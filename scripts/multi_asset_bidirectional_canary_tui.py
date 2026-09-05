"""Attach to or launch the bidirectional cohort with its read-only TUI."""

from __future__ import annotations

import argparse
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Literal

from hypervector.live.canary_supervisor import (
    CanarySupervisorError,
    LedgerStartupSnapshot,
    capture_ledger_start,
    signal_process_group as _signal_process_group,
    wait_for_fresh_configuration_identity,
)
from hypervector.live.cohort_accounting_rollover import (
    load_required_accounting_epoch,
)
from hypervector.live.cohort_monitor_identity import (
    active_ledger_identity,
    fresh_checkpoint_document,
    require_matching_checkpoint_attachment,
)
from hypervector.live.cohort_tui_commands import (
    CHECKPOINT_OUTPUT as _CHECKPOINT_OUTPUT,
    MultiAssetTuiLaunch,
    audit_command as _audit_command,
    backend_command as _backend_command,
    checkpoint_command as _checkpoint_command,
    observer_audit_command as _observer_audit_command,
    observer_checkpoint_command as _observer_checkpoint_command,
    observer_command as _observer_command,
    index_observer_dependency_command as _index_observer_dependency_command,
    require_live_provider_dependencies as _require_live_provider_dependencies,
    require_checkpoint_accounting_epoch as _require_checkpoint_accounting_epoch,
    tui_command as _tui_command,
)
from hypervector.live.cohort_tui_dependency_supervision import (
    start_owned_dependency,
    stop_owned_dependency,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.runtime_env import credential_presence_from_env, load_dotenv_if_present
from hypervector.runtime_lock import cohort_checkpoint_writer_active
from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch

_DEFAULT_CONFIG = Path(
    "configs/multi_asset_bidirectional_evidence_roster_canary_v36.toml"
)
_DEFAULT_BACKTEST_LAB = Path("../backtest-lab/backtest_lab")
_BACKEND_LOG = Path("data/runtime/bidirectional_cohort/backend.log")
_CHECKPOINT_LOG = Path("data/runtime/bidirectional_cohort/checkpoint.log")
_DEPENDENCY_LOG = Path("data/runtime/bidirectional_cohort/spcx_observer.log")
_DEFAULT_STARTUP_TIMEOUT_SECONDS = 900.0
_CHECKPOINT_FRESHNESS_SECONDS = 90.0


def build_parser() -> argparse.ArgumentParser:
    """Build an observe-default and explicitly armed live supervisor."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("observe", "monitor", "live"),
        default="observe",
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--staged-config",
        type=Path,
        help="optional report-only next profile to compare with the active monitor ledger",
    )
    parser.add_argument(
        "--growth-preflight",
        type=Path,
        help="optional read-only sizing evidence for the staged monitor profile",
    )
    parser.add_argument(
        "--backtest-lab-root",
        type=Path,
        default=_DEFAULT_BACKTEST_LAB,
    )
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--i-accept-live-risk", action="store_true")
    parser.add_argument("--accounting-epoch-bundle", type=Path)
    parser.add_argument("--resume-transition-drain", action="store_true")
    parser.add_argument("--refresh-ms", type=int, default=500)
    parser.add_argument(
        "--startup-timeout-seconds",
        type=float,
        default=_DEFAULT_STARTUP_TIMEOUT_SECONDS,
    )
    return parser


def resolve_launch(
    args: argparse.Namespace,
    *,
    credentials_present: bool,
) -> MultiAssetTuiLaunch:
    """Resolve an execution-incapable monitor or one armed live cohort."""
    mode, config, staged_config = _load_launch_configs(args)
    _validate_launch_args(args, mode, config, staged_config, credentials_present)
    accounting_epoch = _launch_accounting_epoch(args, config, staged_config)
    return _resolved_launch(args, mode, config, staged_config, accounting_epoch)


def _load_launch_configs(
    args: argparse.Namespace,
) -> tuple[
    Literal["observe", "live"], MultiAssetLiveConfig, MultiAssetLiveConfig | None
]:
    if args.mode == "monitor" and args.config is None:
        raise MultiAssetLiveConfigError(
            "monitor requires --config bound to the active backend profile"
        )
    if args.config is None:
        args.config = _DEFAULT_CONFIG
    mode: Literal["observe", "live"] = "live" if args.mode == "live" else "observe"
    config = load_multi_asset_live_config(
        args.config,
        mode=mode,
        enabled=args.enabled,
        accepts_live_risk=args.i_accept_live_risk,
    )
    if args.staged_config is not None and args.mode != "monitor":
        raise MultiAssetLiveConfigError("--staged-config requires monitor mode")
    if args.growth_preflight is not None and args.staged_config is None:
        raise MultiAssetLiveConfigError(
            "--growth-preflight requires --staged-config in monitor mode"
        )
    staged_config = (
        load_multi_asset_live_config(args.staged_config, mode="observe")
        if args.staged_config is not None
        else None
    )
    return mode, config, staged_config


def _validate_launch_args(
    args: argparse.Namespace,
    mode: Literal["observe", "live"],
    config: MultiAssetLiveConfig,
    staged_config: MultiAssetLiveConfig | None,
    credentials_present: bool,
) -> None:
    if (
        staged_config is not None
        and staged_config.cohort_ledger != config.cohort_ledger
    ):
        raise MultiAssetLiveConfigError(
            "active and staged profiles must use the same cohort ledger"
        )
    if mode == "live":
        config.require_live_start(credentials_present=credentials_present)
    elif args.resume_transition_drain:
        raise MultiAssetLiveConfigError("transition drain recovery requires live mode")
    if args.startup_timeout_seconds <= 0.0 or args.refresh_ms < 100:
        raise MultiAssetLiveConfigError("invalid TUI refresh or startup timeout")
    if args.mode == "observe" and args.accounting_epoch_bundle is not None:
        raise MultiAssetLiveConfigError(
            "--accounting-epoch-bundle requires live or monitor mode"
        )


def _launch_accounting_epoch(
    args: argparse.Namespace,
    config: MultiAssetLiveConfig,
    staged_config: MultiAssetLiveConfig | None,
) -> CohortAccountingEpoch | None:
    successor = (
        staged_config
        if args.mode == "monitor"
        and staged_config
        and args.accounting_epoch_bundle is not None
        else config
    )
    return (
        None
        if args.mode == "observe"
        else load_required_accounting_epoch(args.accounting_epoch_bundle, successor)
    )


def _resolved_launch(
    args: argparse.Namespace,
    mode: Literal["observe", "live"],
    config: MultiAssetLiveConfig,
    staged_config: MultiAssetLiveConfig | None,
    accounting_epoch: CohortAccountingEpoch | None,
) -> MultiAssetTuiLaunch:
    backend = (
        _backend_command(args, config)
        if mode == "live"
        else _observer_command(args)
        if args.mode == "observe"
        else None
    )
    return MultiAssetTuiLaunch(
        config=config,
        staged_config=staged_config,
        backend_command=backend,
        checkpoint_command=(
            _checkpoint_command(
                config,
                staged_config=staged_config,
                accounting_epoch_bundle=args.accounting_epoch_bundle,
            )
            if mode == "live" or args.mode == "monitor"
            else _observer_checkpoint_command(config)
            if args.mode == "observe"
            else None
        ),
        tui_command=_tui_command(
            args,
            config,
            config.cohort_ledger,
            include_checkpoint=True,
        ),
        audit_command=(
            _audit_command(config)
            if mode == "live"
            else _observer_audit_command(config)
            if args.mode == "observe"
            else None
        ),
        startup_timeout_seconds=args.startup_timeout_seconds,
        accounting_epoch=accounting_epoch,
        dependency_command=(
            _index_observer_dependency_command(config) if mode == "live" else None
        ),
    )


def run_supervisor(launch: MultiAssetTuiLaunch) -> int:
    """Attach directly or supervise exactly one live backend and read-only TUI."""
    if launch.backend_command is None:
        return _run_monitor(launch)
    if launch.config.stop_file.exists():
        raise MultiAssetLiveConfigError(
            f"operator stop file exists; inspect before removing: {launch.config.stop_file}"
        )
    dependency = (
        _start_owned_dependency(
            launch.dependency_command,
            launch.config,
            timeout_seconds=launch.startup_timeout_seconds,
        )
        if launch.dependency_command is not None
        else None
    )
    try:
        return _run_live_supervisor(launch)
    finally:
        if dependency is not None:
            _stop_owned_dependency(dependency)


def _run_live_supervisor(launch: MultiAssetTuiLaunch) -> int:
    """Supervise the backend, checkpoint writer, TUI, and final audit."""
    snapshot = capture_ledger_start(launch.config.cohort_ledger)
    _BACKEND_LOG.parent.mkdir(parents=True, exist_ok=True)
    checkpoint: subprocess.Popen[bytes] | None = None
    checkpoint_failure: str | None = None
    checkpoint_command = launch.checkpoint_command
    audit_command = launch.audit_command
    with _BACKEND_LOG.open("ab", buffering=0) as backend_log:
        backend = subprocess.Popen(
            launch.backend_command,
            stdout=backend_log,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_backend(backend, launch, snapshot)
            if checkpoint_command is not None and launch.config.mode == "live":
                checkpoint_command = _bind_run_to_active_backend(
                    checkpoint_command,
                    launch.config,
                    command_name="checkpoint",
                )
            if audit_command is not None and launch.config.mode == "live":
                audit_command = _bind_run_to_active_backend(
                    audit_command,
                    launch.config,
                    command_name="audit",
                )
            if checkpoint_command is not None:
                checkpoint = _start_checkpoint_monitor(checkpoint_command)
            tui_returncode = subprocess.run(launch.tui_command, check=False).returncode
        finally:
            if checkpoint is not None:
                checkpoint_failure = _stop_checkpoint_monitor(checkpoint)
            _stop_owned_backend(backend, launch.config)
    final_checkpoint_failure = (
        _publish_final_checkpoint(checkpoint_command)
        if checkpoint_command is not None
        else None
    )
    if audit_command is not None:
        _publish_audit(audit_command)
    failure = checkpoint_failure or final_checkpoint_failure
    if failure is not None:
        raise RuntimeError(failure)
    return tui_returncode


def _start_owned_dependency(
    command: tuple[str, ...],
    config: MultiAssetLiveConfig,
    *,
    timeout_seconds: float,
) -> subprocess.Popen[bytes] | None:
    """Start the unsigned observer only when no fresh external instance exists."""
    return start_owned_dependency(
        command,
        config,
        timeout_seconds=timeout_seconds,
        log_path=_DEPENDENCY_LOG,
        health_check=_require_live_provider_dependencies,
    )


def _stop_owned_dependency(process: subprocess.Popen[bytes]) -> None:
    """Stop only the unsigned observer supervisor started by this TUI."""
    stop_owned_dependency(process)


def _run_monitor(launch: MultiAssetTuiLaunch) -> int:
    """Attach a TUI and recover its report-only checkpoint when stale."""
    checkpoint: subprocess.Popen[bytes] | None = None
    checkpoint_failure: str | None = None

    def freshness_check() -> bool:
        return (
            _checkpoint_is_fresh(
                launch.config,
                launch.staged_config,
                accounting_epoch=launch.accounting_epoch,
            )
            if launch.accounting_epoch is not None
            else _checkpoint_is_fresh(launch.config, launch.staged_config)
            if launch.staged_config is not None
            else _checkpoint_is_fresh(launch.config)
        )

    checkpoint_fresh = freshness_check()
    if launch.checkpoint_command is not None:
        writer_active = cohort_checkpoint_writer_active(_CHECKPOINT_OUTPUT)
        if (
            writer_active
            and not checkpoint_fresh
            and (
                launch.staged_config is not None or launch.accounting_epoch is not None
            )
        ):
            document = require_matching_checkpoint_attachment(
                _CHECKPOINT_OUTPUT, launch.config, launch.staged_config
            )
            if launch.accounting_epoch is not None:
                _require_checkpoint_accounting_epoch(document, launch.accounting_epoch)
        if not writer_active:
            checkpoint = _start_checkpoint_monitor(
                _bind_run_to_active_backend(
                    launch.checkpoint_command,
                    launch.config,
                    command_name="checkpoint",
                )
            )
    try:
        tui_returncode = subprocess.run(launch.tui_command, check=False).returncode
    finally:
        if checkpoint is not None:
            checkpoint_failure = _stop_checkpoint_monitor(checkpoint)
    if checkpoint_failure is not None:
        raise RuntimeError(checkpoint_failure)
    return tui_returncode


def _checkpoint_is_fresh(
    config: MultiAssetLiveConfig,
    staged_config: MultiAssetLiveConfig | None = None,
    *,
    accounting_epoch: CohortAccountingEpoch | None = None,
) -> bool:
    """Accept only a recent checkpoint bound to the selected backend profile."""
    document = fresh_checkpoint_document(
        _CHECKPOINT_OUTPUT,
        config,
        staged_config,
        maximum_age_seconds=_CHECKPOINT_FRESHNESS_SECONDS,
    )
    if document is None:
        return False
    if accounting_epoch is not None:
        _require_checkpoint_accounting_epoch(document, accounting_epoch)
    return True


def _start_checkpoint_monitor(
    command: tuple[str, ...] | None,
) -> subprocess.Popen[bytes]:
    if command is None:
        raise RuntimeError("cohort checkpoint command is missing")
    _CHECKPOINT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _CHECKPOINT_LOG.open("ab", buffering=0) as checkpoint_log:
        return subprocess.Popen(
            command,
            stdout=checkpoint_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def _bind_run_to_active_backend(
    command: tuple[str, ...],
    config: MultiAssetLiveConfig,
    *,
    command_name: str,
) -> tuple[str, ...]:
    """Bind one report-only command to the backend run proven after startup."""
    run_id = active_ledger_identity(config).run_id
    if "--run-id" not in command:
        return (*command, "--run-id", run_id)
    index = command.index("--run-id")
    if index + 1 >= len(command):
        raise MultiAssetLiveConfigError(f"{command_name} --run-id value is missing")
    rebound = list(command)
    rebound[index + 1] = run_id
    return tuple(rebound)


def _stop_checkpoint_monitor(process: subprocess.Popen[bytes]) -> str | None:
    if process.poll() is not None:
        return (
            None
            if process.returncode == 0
            else f"checkpoint observer exited with {process.returncode}; "
            f"inspect {_CHECKPOINT_LOG}"
        )
    _signal_process_group(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        _signal_process_group(process.pid, signal.SIGKILL)
        process.wait(timeout=5.0)
        return f"checkpoint observer required forced termination; inspect {_CHECKPOINT_LOG}"
    return None


def _publish_audit(command: tuple[str, ...] | None) -> None:
    if command is None:
        raise RuntimeError("live cohort audit command is missing")
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"cohort stopped but immutable audit failed with {result.returncode}"
        )


def _publish_final_checkpoint(command: tuple[str, ...] | None) -> str | None:
    if command is None:
        return "cohort stopped but final checkpoint command is missing"
    bounded = (
        ("--current-run-only",)
        if "scripts/multi_asset_bidirectional_live_checkpoint.py" in command
        else ()
    )
    result = subprocess.run(
        (*command, "--once", *bounded),
        check=False,
    )
    if result.returncode == 0:
        return None
    return (
        f"cohort stopped but final checkpoint failed with {result.returncode}; "
        f"inspect {_CHECKPOINT_LOG}"
    )


def _wait_for_backend(
    backend: subprocess.Popen[bytes],
    launch: MultiAssetTuiLaunch,
    snapshot: LedgerStartupSnapshot,
) -> None:
    wait_for_fresh_configuration_identity(
        backend,
        launch.config.cohort_ledger,
        snapshot=snapshot,
        expected_profile_fingerprint=launch.config.profile_fingerprint,
        expected_live_armed=launch.config.mode == "live",
        timeout_seconds=launch.startup_timeout_seconds,
        backend_label=(
            "multi-asset bidirectional live cohort"
            if launch.config.mode == "live"
            else "multi-asset bidirectional observer"
        ),
        log_path=_BACKEND_LOG,
        sleep_fn=time.sleep,
    )


def _stop_owned_backend(
    backend: subprocess.Popen[bytes],
    config: MultiAssetLiveConfig,
) -> None:
    if backend.poll() is not None:
        return
    config.stop_file.parent.mkdir(parents=True, exist_ok=True)
    config.stop_file.write_text("operator_tui_exit\n", encoding="utf-8")
    try:
        backend.wait(timeout=30.0)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "live cohort did not stop within 30s and was left running; "
            f"STOP remains at {config.stop_file}; inspect {_BACKEND_LOG}"
        ) from exc
    config.stop_file.unlink(missing_ok=True)
    if backend.returncode not in {0, 130}:
        raise RuntimeError(
            f"live cohort stopped with {backend.returncode}; inspect {_BACKEND_LOG}"
        )


def main() -> int:
    """Load secret presence only and run the requested TUI lifecycle."""
    load_dotenv_if_present()
    presence = credential_presence_from_env()
    try:
        launch = resolve_launch(
            build_parser().parse_args(),
            credentials_present=presence.wallet_configured
            and presence.signing_key_configured,
        )
        return run_supervisor(launch)
    except (CanarySupervisorError, MultiAssetLiveConfigError, RuntimeError) as exc:
        print(f"cohort TUI start refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
