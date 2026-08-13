#!/usr/bin/env python3
"""Launch the Apex MM live backend and read-only TUI in one terminal."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import FrameType

from hypervector.live.apex_mm_live_config import (
    ApexMMLiveConfig,
    ApexMMLiveConfigError,
    load_apex_mm_live_config,
)
from hypervector.live.canary_supervisor import (
    CanarySupervisorError,
    capture_ledger_start,
    wait_for_fresh_configuration_identity,
)
from hypervector.runtime_env import credential_presence_from_env, load_dotenv_if_present

_CONFIG = Path("configs/apex_regime_mm_canary.toml")
_BACKEND_LOG = Path("data/runtime/apex_regime_mm/backend.log")
_SHUTDOWN_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class ApexMMCanaryLaunch:
    """Resolved backend/TUI commands and lifecycle paths."""

    config: ApexMMLiveConfig
    backend_command: tuple[str, ...]
    tui_command: tuple[str, ...]
    startup_timeout_seconds: float


def build_parser() -> argparse.ArgumentParser:
    """Build a live-only, fail-closed supervisor command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--i-accept-live-risk", action="store_true")
    parser.add_argument("--refresh-ms", type=int, default=500)
    parser.add_argument("--startup-timeout-seconds", type=float, default=30.0)
    return parser


def resolve_launch(
    args: argparse.Namespace,
    *,
    credentials_present: bool,
) -> ApexMMCanaryLaunch:
    """Resolve child commands only after enforcing live authority gates."""
    config = load_apex_mm_live_config(
        args.config,
        enabled=args.enabled,
        accepts_live_risk=args.i_accept_live_risk,
    )
    config.require_live_start(credentials_present=credentials_present)
    if args.startup_timeout_seconds <= 0.0:
        raise ApexMMLiveConfigError("startup timeout seconds must be positive")
    return ApexMMCanaryLaunch(
        config,
        _backend_command(args),
        _tui_command(args, config.backend_ledger),
        args.startup_timeout_seconds,
    )


def _backend_command(args: argparse.Namespace) -> tuple[str, ...]:
    return (
        sys.executable,
        "scripts/apex_regime_mm_live.py",
        "--config",
        str(args.config),
        "--enabled",
        "--i-accept-live-risk",
    )


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
        "BTC",
        "--timeframe",
        "1m",
        "--live",
        "--refresh-ms",
        str(args.refresh_ms),
        "--backend-ledger",
        str(ledger),
    )


def run_supervisor(launch: ApexMMCanaryLaunch) -> int:
    """Own both children and request verified backend shutdown on TUI exit."""
    stop_file = launch.config.stop_file
    if stop_file.exists():
        raise RuntimeError(
            f"canary stop file already exists; inspect before removing: {stop_file}"
        )
    ledger = launch.config.backend_ledger
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
                expected_live_armed=True,
                timeout_seconds=launch.startup_timeout_seconds,
                backend_label="Apex MM",
                log_path=_BACKEND_LOG,
                sleep_fn=time.sleep,
            )
            return subprocess.run(launch.tui_command, check=False).returncode
        finally:
            _stop_owned_backend(backend, stop_file)


def _stop_owned_backend(backend: subprocess.Popen[bytes], stop_file: Path) -> None:
    if backend.poll() is not None:
        return
    stop_file.parent.mkdir(parents=True, exist_ok=True)
    stop_file.write_text("operator_tui_exit\n", encoding="utf-8")
    try:
        backend.wait(timeout=_SHUTDOWN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"live backend did not stop within {_SHUTDOWN_TIMEOUT_SECONDS:g}s "
            "and was left running; "
            f"STOP remains at {stop_file}; inspect {_BACKEND_LOG}"
        ) from exc
    stop_file.unlink(missing_ok=True)
    if backend.returncode not in {0, 130}:
        raise RuntimeError(
            f"live backend stopped with {backend.returncode}; inspect {_BACKEND_LOG}"
        )


def main() -> int:
    """Load credential presence and supervise the explicitly armed canary."""
    previous_sigterm = signal.signal(signal.SIGTERM, _request_verified_cleanup)
    try:
        load_dotenv_if_present()
        presence = credential_presence_from_env()
        try:
            launch = resolve_launch(
                build_parser().parse_args(),
                credentials_present=(
                    presence.wallet_configured and presence.signing_key_configured
                ),
            )
        except ApexMMLiveConfigError as exc:
            print(f"canary start refused: {exc}", file=sys.stderr)
            return 2
        try:
            return run_supervisor(launch)
        except (CanarySupervisorError, RuntimeError) as exc:
            print(f"canary start refused: {exc}", file=sys.stderr)
            return 2
    except KeyboardInterrupt:
        return 130
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)


def _request_verified_cleanup(_signum: int, _frame: FrameType | None) -> None:
    raise KeyboardInterrupt


if __name__ == "__main__":
    raise SystemExit(main())
