"""Execution-heartbeat truth for the rolling live checkpoint."""

from __future__ import annotations

from datetime import datetime, timedelta
from copy import deepcopy

from hypervector.research.cohort_live_checkpoint import build_live_checkpoint
from test_cohort_live_checkpoint import _active_asset_rows
from test_multi_asset_live_audit import _asset_rows, _cohort_rows

_RUN_ID = "cohort-live-a"
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")


def test_fresh_sidecar_cannot_mask_stale_execution_heartbeat() -> None:
    """Active asset records plus an old running heartbeat report backend stale."""
    cohort = _cohort_rows()
    heartbeat_at = datetime.fromisoformat(str(cohort[-1]["observed_at_utc"]))

    checkpoint = build_live_checkpoint(
        cohort,
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=heartbeat_at + timedelta(seconds=61),
        heartbeat_stale_after_seconds=60.0,
    )

    lifecycle = checkpoint["lifecycle"]
    assert lifecycle["state"] == "backend_heartbeat_stale"
    assert lifecycle["backend_process_health"] == "stale"
    assert lifecycle["cohort_heartbeat_age_seconds"] == 61.0


def test_recent_execution_heartbeat_remains_running_consistent() -> None:
    """The same evidence is healthy while its backend heartbeat is recent."""
    cohort = _cohort_rows()
    heartbeat_at = datetime.fromisoformat(str(cohort[-1]["observed_at_utc"]))

    checkpoint = build_live_checkpoint(
        cohort,
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=heartbeat_at + timedelta(seconds=59),
        heartbeat_stale_after_seconds=60.0,
    )

    lifecycle = checkpoint["lifecycle"]
    assert lifecycle["state"] == "running_consistent"
    assert lifecycle["backend_process_health"] == "healthy"
    assert lifecycle["cohort_heartbeat_age_seconds"] == 59.0


def test_terminal_assets_keep_terminal_precedence_over_old_heartbeat() -> None:
    """A completed stop remains explicit instead of becoming process ambiguity."""
    cohort = _cohort_rows()
    heartbeat_at = datetime.fromisoformat(str(cohort[-1]["observed_at_utc"]))

    checkpoint = build_live_checkpoint(
        cohort,
        {symbol: _asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=heartbeat_at + timedelta(seconds=61),
        heartbeat_stale_after_seconds=60.0,
    )

    assert checkpoint["lifecycle"]["state"] == (
        "stale_running_heartbeat_after_asset_stop"
    )


def test_runtime_fault_immediately_overrides_recent_running_heartbeat() -> None:
    """A durable fatal event cannot look healthy during the freshness window."""
    cohort = _cohort_rows()
    fault = deepcopy(cohort[-1])
    fault["sequence"] = int(fault["sequence"]) + 1
    fault_at = datetime.fromisoformat(str(fault["observed_at_utc"])) + timedelta(
        seconds=1
    )
    fault["observed_at_utc"] = fault_at.isoformat()
    fault["event_type"] = "runtime_fault"
    fault["payload"] = {
        "status": "faulted",
        "exception_type": "RuntimeError",
        "orders_attempted": False,
        "detail": "inspect backend process log",
    }
    cohort.append(fault)

    checkpoint = build_live_checkpoint(
        cohort,
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=fault_at + timedelta(seconds=1),
        heartbeat_stale_after_seconds=60.0,
    )

    lifecycle = checkpoint["lifecycle"]
    assert lifecycle["state"] == "backend_runtime_fault"
    assert lifecycle["backend_process_health"] == "faulted"
    assert lifecycle["runtime_fault_exception_type"] == "RuntimeError"
