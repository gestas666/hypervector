"""Supervise the shadow backend while the read-only TUI owns the terminal."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from hypervector.infra import ensure_data_layout

BACKEND_LOG_NAME = "hypervelocity-shadow.log"
DECISIONS_RELATIVE = Path("paper/decisions/decisions.jsonl")


@dataclass(frozen=True)
class TuiLaunchResult:
    """Exit status and durable backend log for a unified TUI session."""

    tui_returncode: int
    backend_returncode: int
    backend_log: Path


def build_backend_command(
    *,
    data_root: Path,
    config_path: Path,
) -> list[str]:
    """Build the no-submit backend child command."""
    return [
        sys.executable,
        "-u",
        "-m",
        "hypervector",
        "--data-root",
        str(data_root.resolve()),
        "hypervelocity-shadow-run",
        "--config",
        str(config_path.resolve()),
    ]


def build_tui_command(
    *,
    data_root: Path,
    symbol: str,
    timeframe: str,
    refresh_ms: int,
    tui_binary: Path | None = None,
) -> list[str]:
    """Build a foreground TUI command using a binary or Cargo fallback."""
    prefix = _tui_prefix(tui_binary)
    return [
        *prefix,
        "--symbol",
        symbol,
        "--timeframe",
        timeframe,
        "--live",
        "--refresh-ms",
        str(refresh_ms),
        "--data-root",
        str(data_root.resolve()),
    ]


def supervise_hypervelocity_tui(
    *,
    data_root: Path,
    backend_command: Sequence[str],
    tui_command: Sequence[str],
    startup_timeout_seconds: float,
) -> TuiLaunchResult:
    """Start backend, wait for telemetry, run TUI, then reap the backend."""
    if startup_timeout_seconds <= 0.0:
        raise ValueError("startup_timeout_seconds must be positive")
    paths = ensure_data_layout(data_root)
    decisions_path = paths.root / DECISIONS_RELATIVE
    initial_size = _file_size(decisions_path)
    backend_log = paths.root / "paper" / BACKEND_LOG_NAME
    project_root = _project_root()
    with backend_log.open("a", encoding="utf-8") as log_handle:
        child = subprocess.Popen(
            list(backend_command),
            cwd=project_root,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            _wait_for_backend(child, decisions_path, initial_size, startup_timeout_seconds)
            tui = subprocess.run(list(tui_command), cwd=project_root, check=False)
        finally:
            backend_returncode = _stop_backend(child)
    if tui.returncode != 0:
        raise RuntimeError(f"TUI exited with status {tui.returncode}")
    return TuiLaunchResult(tui.returncode, backend_returncode, backend_log)


def _tui_prefix(tui_binary: Path | None) -> list[str]:
    if tui_binary is not None:
        return [str(tui_binary)]
    configured = os.environ.get("HYPERVECTOR_TUI_BIN")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"HYPERVECTOR_TUI_BIN not found: {path}")
        return [str(path.resolve())]
    root = _project_root()
    for relative in ("target/release/tui-regime-detector", "target/debug/tui-regime-detector"):
        candidate = root / relative
        if candidate.is_file():
            return [str(candidate)]
    return ["cargo", "run", "-q", "-p", "hypervector-tui", "--bin", "tui-regime-detector", "--"]


def _wait_for_backend(
    child: subprocess.Popen[str],
    decisions_path: Path,
    initial_size: int,
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        returncode = child.poll()
        if returncode is not None:
            raise RuntimeError(
                f"backend exited before telemetry with status {returncode}"
            )
        if _file_size(decisions_path) > initial_size:
            return
        time.sleep(0.05)
    raise RuntimeError(f"backend telemetry not ready after {timeout_seconds:.1f}s")


def _stop_backend(child: subprocess.Popen[str]) -> int:
    returncode = child.poll()
    if returncode is not None:
        return returncode
    child.terminate()
    try:
        return child.wait(timeout=15.0)
    except subprocess.TimeoutExpired:
        child.kill()
        return child.wait(timeout=5.0)


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]
