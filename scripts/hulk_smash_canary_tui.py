#!/usr/bin/env python3
"""Launch the Hulk Smash observer or live canary with its read-only TUI."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import FrameType
from typing import Literal

from hypervector.live.hulk_smash_live_config import (
    HulkSmashLiveConfig,
    HulkSmashLiveConfigError,
    load_hulk_smash_live_config,
)
from hypervector.live.canary_supervisor import (
    CanarySupervisorError,
    capture_ledger_start,
    wait_for_fresh_configuration_identity,
)
from hypervector.runtime_env import (
    credential_presence_from_env,
    load_dotenv_if_present,
    load_wallet_env_if_present,
)

_CONFIG = Path("configs/hulk_smash_short_robust_v3_canary.toml")
_BACKEND_LOG = Path("data/runtime/hulk_smash/backend.log")
_SHUTDOWN_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class HulkSmashCanaryLaunch:
    """Resolved backend/TUI commands and immutable strategy configuration."""

    config: HulkSmashLiveConfig
    backend_command: tuple[str, ...]
    tui_command: tuple[str, ...]
    startup_timeout_seconds: float


def build_parser() -> argparse.ArgumentParser:
    """Build an observe-default, explicitly armed live command surface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("observe", "live"), default="observe")
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--i-accept-live-risk", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--refresh-ms", type=int, default=500)
    parser.add_argument("--startup-timeout-seconds", type=float, default=30.0)
    return parser


def resolve_launch(
    args: argparse.Namespace,
    *,
    wallet_configured: bool,
    signing_key_configured: bool,
) -> HulkSmashCanaryLaunch:
    """Resolve mode-specific commands after all authority checks pass."""
    mode: Literal["observe", "live"] = args.mode
    config = load_hulk_smash_live_config(
        args.config,
        mode=mode,
        enabled=args.enabled,
        accepts_live_risk=args.i_accept_live_risk,
    )
    if mode == "live":
        config.require_live_start(
            credentials_present=wallet_configured and signing_key_configured
        )
    elif not wallet_configured:
        raise HulkSmashLiveConfigError(
            "Hulk observer requires a configured public wallet address"
        )
    if args.startup_timeout_seconds <= 0.0:
        raise HulkSmashLiveConfigError("startup timeout seconds must be positive")
    return HulkSmashCanaryLaunch(
        config=config,
        backend_command=_backend_command(args, mode),
        tui_command=_tui_command(args, config),
        startup_timeout_seconds=args.startup_timeout_seconds,
    )


def _backend_command(
    args: argparse.Namespace,
    mode: Literal["observe", "live"],
) -> tuple[str, ...]:
    script = (
        "scripts/hulk_smash_live.py"
        if mode == "live"
        else "scripts/hulk_smash_observe.py"
    )
    command = [
        sys.executable,
        "-u",
        script,
        "--config",
        str(args.config),
        "--poll-seconds",
        str(args.poll_seconds),
    ]
    if mode == "live":
        command.extend(("--enabled", "--i-accept-live-risk"))
    return tuple(command)


def _tui_command(
    args: argparse.Namespace,
    config: HulkSmashLiveConfig,
) -> tuple[str, ...]:
    return (
        "cargo",
        "run",
        "-q",
        "-p",
        "hypervector-tui",
        "--bin",
        "tui-regime-detector",
        "--",
        "--symbol",
        config.symbol,
        "--timeframe",
        config.signal_timeframe,
        "--live",
        "--refresh-ms",
        str(args.refresh_ms),
        "--backend-ledger",
        str(config.backend_ledger),
    )


def run_supervisor(launch: HulkSmashCanaryLaunch) -> int:
    """Start the backend, await fresh telemetry, and own verified shutdown."""
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
                expected_live_armed=launch.config.mode == "live",
                timeout_seconds=launch.startup_timeout_seconds,
                backend_label="Hulk",
                log_path=_BACKEND_LOG,
                sleep_fn=time.sleep,
            )
            return subprocess.run(launch.tui_command, check=False).returncode
        finally:
            _stop_owned_backend(backend, stop_file, launch.config)


def _stop_owned_backend(
    backend: subprocess.Popen[bytes],
    stop_file: Path,
    config: HulkSmashLiveConfig,
) -> None:
    existing_returncode = backend.poll()
    if existing_returncode is not None:
        if existing_returncode not in {0, 130}:
            raise RuntimeError(
                f"{config.mode} backend stopped with {existing_returncode}; "
                f"inspect {_BACKEND_LOG}"
            )
        return
    stop_file.parent.mkdir(parents=True, exist_ok=True)
    stop_file.write_text("operator_tui_exit\n", encoding="utf-8")
    try:
        backend.wait(timeout=_SHUTDOWN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        if config.mode == "live":
            raise RuntimeError(
                f"live backend did not stop within {_SHUTDOWN_TIMEOUT_SECONDS:g}s "
                "and was left running; "
                f"STOP remains at {stop_file}; inspect {_BACKEND_LOG}"
            ) from exc
        backend.terminate()
        backend.wait(timeout=5.0)
    stop_file.unlink(missing_ok=True)
    if config.mode == "live" and backend.returncode not in {0, 130}:
        raise RuntimeError(
            f"live backend stopped with {backend.returncode}; inspect {_BACKEND_LOG}"
        )


def main() -> int:
    """Load credential presence and supervise the requested Hulk mode."""
    previous_sigterm = signal.signal(signal.SIGTERM, _request_verified_cleanup)
    try:
        args = build_parser().parse_args()
        if args.mode == "live":
            load_dotenv_if_present()
        else:
            load_wallet_env_if_present()
        presence = credential_presence_from_env()
        try:
            launch = resolve_launch(
                args,
                wallet_configured=presence.wallet_configured,
                signing_key_configured=presence.signing_key_configured,
            )
            return run_supervisor(launch)
        except (CanarySupervisorError, HulkSmashLiveConfigError, RuntimeError) as exc:
            print(f"Hulk canary start refused: {exc}", file=sys.stderr)
            return 2
    except KeyboardInterrupt:
        return 130
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)


def _request_verified_cleanup(_signum: int, _frame: FrameType | None) -> None:
    raise KeyboardInterrupt


if __name__ == "__main__":
    raise SystemExit(main())
