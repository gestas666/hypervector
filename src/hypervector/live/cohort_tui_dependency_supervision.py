"""Lifecycle supervision for unsigned external TUI signal dependencies."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
import signal
import subprocess
import time

from hypervector.live.canary_supervisor import signal_process_group
from hypervector.live.hip3_provider_availability import Hip3ObserverUnavailableError
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
)

HealthCheck = Callable[[MultiAssetLiveConfig], None]


def start_owned_dependency(
    command: tuple[str, ...],
    config: MultiAssetLiveConfig,
    *,
    timeout_seconds: float,
    log_path: Path,
    health_check: HealthCheck,
) -> subprocess.Popen[bytes] | None:
    """Start an unsigned dependency only when no fresh instance exists."""
    if _healthy_or_startable(config, health_check):
        return None
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab", buffering=0) as stream:
        process = subprocess.Popen(
            command,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    with ExitStack() as cleanup:
        cleanup.callback(stop_owned_dependency, process)
        _wait_until_healthy(process, config, timeout_seconds, log_path, health_check)
        cleanup.pop_all()
        return process


def _wait_until_healthy(
    process: subprocess.Popen[bytes],
    config: MultiAssetLiveConfig,
    timeout_seconds: float,
    log_path: Path,
    health_check: HealthCheck,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise MultiAssetLiveConfigError(
                f"pressure observer exited with {process.returncode}; inspect {log_path}"
            )
        if _healthy_or_startable(config, health_check):
            return
        time.sleep(0.5)
    raise MultiAssetLiveConfigError(
        f"pressure observer was not fresh within {timeout_seconds:g}s; inspect {log_path}"
    )


def stop_owned_dependency(process: subprocess.Popen[bytes]) -> None:
    """Stop only the unsigned dependency process started by this TUI."""
    if process.poll() is not None:
        return
    signal_process_group(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        signal_process_group(process.pid, signal.SIGKILL)
        process.wait(timeout=5.0)


def _healthy_or_startable(
    config: MultiAssetLiveConfig,
    health_check: HealthCheck,
) -> bool:
    try:
        health_check(config)
        return True
    except (FileNotFoundError, Hip3ObserverUnavailableError):
        return False
