"""Shared durable publication for authority-none lifecycle watchers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.research.report_only_lifecycle_watch import (
    publish_watch_status,
    run_watch_loop,
    validate_watch_snapshot,
)


def test_pending_status_is_atomic_without_snapshot(tmp_path: Path) -> None:
    """An unresolved report must update status without claiming a lifecycle."""
    status = publish_watch_status(
        _report(),
        status_path=tmp_path / "latest.json",
        snapshot_dir=tmp_path / "snapshots",
        run_id="observer-run",
    )

    assert status["watch_state"] == "awaiting_resolution"
    assert status["snapshot"] is None
    assert (tmp_path / "latest.json").is_file()


def test_resolved_status_snapshot_is_idempotent(tmp_path: Path) -> None:
    """The same resolved evidence must publish one immutable snapshot."""
    first = publish_watch_status(
        _report(resolved=True),
        status_path=tmp_path / "latest.json",
        snapshot_dir=tmp_path / "snapshots",
        run_id="observer-run",
    )
    second = publish_watch_status(
        _report(resolved=True),
        status_path=tmp_path / "latest.json",
        snapshot_dir=tmp_path / "snapshots",
        run_id="observer-run",
    )

    assert first["snapshot"] == second["snapshot"]
    assert len(list((tmp_path / "snapshots").glob("*.json"))) == 1
    snapshot = Path(str(first["snapshot"]))
    evidence = validate_watch_snapshot(snapshot, first)
    assert evidence["bytes"] == snapshot.stat().st_size
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    payload["summary"]["resolved"] = 2
    snapshot.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="snapshot state differs"):
        validate_watch_snapshot(snapshot, first)
    snapshot.unlink()
    with pytest.raises(FileNotFoundError, match="snapshot is missing"):
        validate_watch_snapshot(snapshot, first)


def test_live_shaped_report_is_rejected(tmp_path: Path) -> None:
    """Shared publication cannot turn a report into execution authority."""
    report = _report()
    report["contract"]["execution_authority"] = "live"

    with pytest.raises(ValueError, match="report-only contract"):
        publish_watch_status(
            report,
            status_path=tmp_path / "latest.json",
            snapshot_dir=tmp_path / "snapshots",
            run_id="observer-run",
        )


def test_bounded_loop_refreshes_exact_cycle_count() -> None:
    """A bounded watcher must not sleep after its final refresh."""
    calls: list[str] = []

    result = run_watch_loop(
        lambda: calls.append("refresh"),
        interval_seconds=1.0,
        max_cycles=2,
        sleep_fn=lambda value: calls.append(f"sleep:{value}"),
    )

    assert result == 0
    assert calls == ["refresh", "sleep:1.0", "refresh"]


def test_transient_failure_retries_without_counting_a_publication() -> None:
    """A report-only transport outage preserves the last good publication."""
    calls: list[str] = []

    def refresh() -> None:
        calls.append("refresh")
        if calls.count("refresh") == 1:
            raise RuntimeError("temporary venue throttle")

    result = run_watch_loop(
        refresh,
        interval_seconds=1.0,
        max_cycles=1,
        sleep_fn=lambda value: calls.append(f"sleep:{value}"),
        transient_exceptions=(RuntimeError,),
        transient_reason=lambda _exc: "http_429_retry_exhausted",
        transient_reporter=lambda reason, _exc: calls.append(f"degraded:{reason}"),
    )

    assert result == 0
    assert calls == [
        "refresh",
        "degraded:http_429_retry_exhausted",
        "sleep:1.0",
        "refresh",
    ]


def _report(*, resolved: bool = False) -> dict[str, object]:
    executions = [{"decision_time_ms": 1, "net_return_bps": 2.0}] if resolved else []
    return {
        "state": "descriptive_exact_depth_evidence"
        if resolved
        else "awaiting_resolution",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "portfolio_pnl_claimed": False,
            "actual_orders_or_fills_claimed": False,
        },
        "summary": {"resolved": len(executions)},
        "latest_attempts": [],
        "latest_executions": executions,
    }
