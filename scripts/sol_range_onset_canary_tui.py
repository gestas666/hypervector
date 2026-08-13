"""Launch the SOL canary backend and read-only TUI in one terminal."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
import time
from typing import Literal

from hypervector.live.sol_range_onset_config import (
    SolCanaryConfigError,
    SolRangeOnsetConfig,
    load_sol_range_onset_config,
)
from hypervector.live.canary_supervisor import (
    CanarySupervisorError,
    capture_ledger_start,
    wait_for_fresh_configuration_identity,
)
from hypervector.runtime_env import credential_presence_from_env, load_dotenv_if_present

_DEFAULT_CONFIG = Path("configs/sol_range_onset_canary.toml")
_BACKEND_LOG = Path("data/runtime/sol_range_onset_canary/backend.log")


@dataclass(frozen=True)
class SolCanaryLaunch:
    """Resolved backend/TUI commands and lifecycle paths."""

    config: SolRangeOnsetConfig
    backend_command: tuple[str, ...]
    tui_command: tuple[str, ...]
    startup_timeout_seconds: float


def build_parser() -> argparse.ArgumentParser:
    """Build a two-mode, shadow-default supervisor command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("shadow", "live"), default="shadow")
    parser.add_argument("--config", type=Path, default=_DEFAULT_CONFIG)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--i-accept-live-risk", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--lookback-days", type=int, default=5)
    parser.add_argument("--refresh-ms", type=int, default=500)
    parser.add_argument("--startup-timeout-seconds", type=float, default=30.0)
    return parser


def resolve_launch(
    args: argparse.Namespace,
    *,
    credentials_present: bool,
) -> SolCanaryLaunch:
    """Resolve mode-specific commands after enforcing live authority gates."""
    mode: Literal["shadow", "live"] = args.mode
    config = load_sol_range_onset_config(
        args.config,
        mode=mode,
        enabled=args.enabled,
        accepts_live_risk=args.i_accept_live_risk,
    )
    if mode == "live":
        config.require_live_start(credentials_present=credentials_present)
    backend = _backend_command(args, mode)
    ledger = config.live_ledger if mode == "live" else config.backend_ledger
    if args.startup_timeout_seconds <= 0.0:
        raise SolCanaryConfigError("startup timeout seconds must be positive")
    return SolCanaryLaunch(
        config,
        backend,
        _tui_command(args, ledger),
        args.startup_timeout_seconds,
    )


def _backend_command(
    args: argparse.Namespace,
    mode: Literal["shadow", "live"],
) -> tuple[str, ...]:
    script = (
        "scripts/sol_range_onset_live.py"
        if mode == "live"
        else "scripts/sol_range_onset_forward_observer.py"
    )
    command = [
        sys.executable,
        script,
        "--config",
        str(args.config),
        "--poll-seconds",
        str(args.poll_seconds),
        "--lookback-days",
        str(args.lookback_days),
    ]
    if mode == "live":
        command.extend(["--enabled", "--i-accept-live-risk"])
    return tuple(command)


def _tui_command(args: argparse.Namespace, ledger: Path) -> tuple[str, ...]:
    return (
        "cargo",
        "run",
        "-p",
        "hypervector-tui",
        "--bin",
        "tui-regime-detector",
        "--",
        "--symbol",
        "SOL",
        "--timeframe",
        "1m",
        "--live",
        "--refresh-ms",
        str(args.refresh_ms),
        "--backend-ledger",
        str(ledger),
    )


def run_supervisor(launch: SolCanaryLaunch) -> int:
    """Own both child processes and stop the backend when this TUI exits."""
    stop_file = launch.config.authoritative_stop_file
    if stop_file.exists():
        raise RuntimeError(
            f"canary stop file already exists; inspect before removing: {stop_file}"
        )
    ledger = (
        launch.config.live_ledger
        if launch.config.mode == "live"
        else launch.config.backend_ledger
    )
    snapshot = capture_ledger_start(ledger)
    _BACKEND_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _BACKEND_LOG.open("ab", buffering=0) as backend_log:
        backend = subprocess.Popen(
            launch.backend_command,
            stdout=backend_log,
            stderr=subprocess.STDOUT,
        )
        try:
            wait_for_fresh_configuration_identity(
                backend,
                ledger,
                snapshot=snapshot,
                expected_profile_fingerprint=launch.config.profile_fingerprint,
                expected_live_armed=launch.config.mode == "live",
                timeout_seconds=launch.startup_timeout_seconds,
                backend_label=f"SOL {launch.config.mode}",
                log_path=_BACKEND_LOG,
                sleep_fn=time.sleep,
            )
            return subprocess.run(launch.tui_command, check=False).returncode
        finally:
            _stop_owned_backend(backend, stop_file, launch.config)


def _stop_owned_backend(
    backend: subprocess.Popen[bytes],
    stop_file: Path,
    config: SolRangeOnsetConfig,
) -> None:
    if backend.poll() is not None:
        return
    stop_file.parent.mkdir(parents=True, exist_ok=True)
    stop_file.write_text("operator_tui_exit\n", encoding="utf-8")
    try:
        backend.wait(timeout=20.0)
    except subprocess.TimeoutExpired as exc:
        if config.mode == "live":
            raise RuntimeError(
                "live backend did not stop within 20s and was left running; "
                f"STOP remains at {stop_file}; inspect {_BACKEND_LOG}"
            ) from exc
        backend.terminate()
        backend.wait(timeout=5.0)
        return
    stop_file.unlink(missing_ok=True)
    if config.mode == "live" and backend.returncode not in {0, 130}:
        raise RuntimeError(
            f"live backend stopped with {backend.returncode}; inspect {_BACKEND_LOG}"
        )


def main() -> int:
    """Load credential presence and supervise the requested canary mode."""
    load_dotenv_if_present()
    presence = credential_presence_from_env()
    try:
        launch = resolve_launch(
            build_parser().parse_args(),
            credentials_present=(
                presence.wallet_configured and presence.signing_key_configured
            ),
        )
    except (CanarySupervisorError, SolCanaryConfigError, RuntimeError) as exc:
        print(f"canary start refused: {exc}", file=sys.stderr)
        return 2
    try:
        return run_supervisor(launch)
    except (CanarySupervisorError, RuntimeError) as exc:
        print(f"canary start refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
