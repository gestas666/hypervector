"""Research imports wait for enough pending evidence, a new fill, or a maximum age."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from hypervector.research import cohort_research_import_gate as gate_module
from hypervector.research.cohort_background_sync import (
    BackgroundResearchSync,
    ResearchSyncError,
)
from hypervector.research.cohort_research_import_gate import ResearchImportGate

_HEARTBEAT = b'{"sequence":1,"event_type":"heartbeat","payload":{}}\n'
_FILL = b'{"sequence":2,"event_type":"fill","payload":{"oid":7}}\n'
_AT = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def _ledgers(tmp_path: Path) -> Path:
    root = tmp_path / "ledgers"
    root.mkdir()
    (root / "decisions.jsonl").write_bytes(_HEARTBEAT)
    (root / "sol.jsonl").write_bytes(_HEARTBEAT)
    return root


def _append(path: Path, data: bytes) -> None:
    with path.open("ab") as handle:
        handle.write(data)


def _imported(
    root: Path, *, minimum: int = 1024, age: float = 600.0
) -> ResearchImportGate:
    gate = ResearchImportGate(
        root, minimum_pending_bytes=minimum, maximum_age_seconds=age
    )
    assert gate.due(0.0)
    gate.submitted(0.0)
    gate.completed(succeeded=True)
    return gate


def test_first_import_is_due_before_any_baseline(tmp_path: Path) -> None:
    """Startup must load the durable archive rather than wait for a threshold."""
    gate = ResearchImportGate(
        _ledgers(tmp_path), minimum_pending_bytes=10**9, maximum_age_seconds=10**9
    )

    assert gate.due(0.0)


def test_small_heartbeat_increment_waits_for_threshold_or_age(tmp_path: Path) -> None:
    """Routine appends below the byte threshold do not rewrite DuckDB indexes."""
    root = _ledgers(tmp_path)
    gate = _imported(root, minimum=1024, age=600.0)
    _append(root / "decisions.jsonl", _HEARTBEAT * 3)

    assert not gate.due(120.0)
    assert not gate.due(599.9)
    assert gate.due(600.0)


def test_pending_bytes_across_ledgers_reach_threshold(tmp_path: Path) -> None:
    """The byte threshold counts every JSONL ledger the importer reads."""
    root = _ledgers(tmp_path)
    minimum = 4 * len(_HEARTBEAT)
    gate = _imported(root, minimum=minimum)
    _append(root / "decisions.jsonl", _HEARTBEAT * 2)
    _append(root / "sol.jsonl", _HEARTBEAT)
    assert not gate.due(120.0)

    (root / "btc.jsonl").write_bytes(_HEARTBEAT)

    assert gate.due(120.0)


@pytest.mark.parametrize(
    "fill",
    [_FILL, b'{"sequence": 2, "event_type": "fill", "payload": {}}\n'],
)
def test_pending_fill_is_imported_at_next_check(tmp_path: Path, fill: bytes) -> None:
    """A new fill refreshes the portfolio archive without waiting for the age."""
    root = _ledgers(tmp_path)
    gate = _imported(root, minimum=10**9)
    _append(root / "sol.jsonl", fill)

    assert gate.due(120.0)


def test_fill_already_covered_by_last_import_does_not_retrigger(
    tmp_path: Path,
) -> None:
    """Only bytes appended after the successful import are scanned for fills."""
    root = _ledgers(tmp_path)
    _append(root / "sol.jsonl", _FILL)
    gate = _imported(root, minimum=10**9)
    _append(root / "sol.jsonl", _HEARTBEAT)

    assert not gate.due(120.0)


def test_fill_marker_split_across_scan_chunks_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bounded chunked reads cannot miss a marker at a chunk boundary."""
    monkeypatch.setattr(gate_module, "_SCAN_CHUNK_BYTES", 7)
    root = _ledgers(tmp_path)
    gate = _imported(root, minimum=10**9)
    _append(root / "sol.jsonl", _HEARTBEAT + _FILL)

    assert gate.due(120.0)


def test_failed_import_is_due_at_next_check(tmp_path: Path) -> None:
    """A failure never waits for the byte threshold or maximum age."""
    root = _ledgers(tmp_path)
    gate = _imported(root, minimum=10**9)
    assert not gate.due(120.0)
    gate.submitted(120.0)
    gate.completed(succeeded=False)

    assert gate.due(240.0)


def test_age_is_measured_from_last_successful_import(tmp_path: Path) -> None:
    """Age restarts at the latest successful submission, not the first."""
    root = _ledgers(tmp_path)
    gate = _imported(root, minimum=10**9, age=600.0)
    assert gate.due(600.0)
    gate.submitted(600.0)
    gate.completed(succeeded=True)

    assert not gate.due(1_199.0)
    assert gate.due(1_200.0)


@pytest.mark.parametrize("change", ["truncate", "remove"])
def test_shrunk_or_removed_ledger_is_due_for_integrity_report(
    tmp_path: Path, change: str
) -> None:
    """The importer, not the gate, reports truncation or a vanished source."""
    root = _ledgers(tmp_path)
    gate = _imported(root, minimum=10**9)
    if change == "truncate":
        (root / "sol.jsonl").write_bytes(b"")
    else:
        (root / "sol.jsonl").unlink()

    assert gate.due(120.0)


def test_unreadable_ledgers_are_due(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stat failure imports so the worker reports the actual error."""
    gate = _imported(_ledgers(tmp_path), minimum=10**9)

    def unreadable(_root: Path) -> dict[Path, int]:
        raise OSError("ledger root unavailable")

    monkeypatch.setattr(gate_module, "_ledger_sizes", unreadable)

    assert gate.due(120.0)


def test_unreadable_ledgers_at_submission_make_next_check_due(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a recorded baseline the gate cannot know what was imported."""
    root = _ledgers(tmp_path)
    gate = _imported(root, minimum=10**9)

    def unreadable(_root: Path) -> dict[Path, int]:
        raise OSError("ledger root unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(gate_module, "_ledger_sizes", unreadable)
        gate.submitted(120.0)
    gate.completed(succeeded=True)

    assert gate.due(240.0)


def test_partial_fill_line_at_submission_is_rescanned_next_check(
    tmp_path: Path,
) -> None:
    """The importer skips a torn tail, so its fill marker must stay pending."""
    root = _ledgers(tmp_path)
    gate = _imported(root, minimum=10**9)
    torn = len(_FILL) // 2 + 10
    assert b'"event_type":"fill"' in _FILL[:torn]
    _append(root / "sol.jsonl", _FILL[:torn])
    assert gate.due(120.0)
    gate.submitted(120.0)
    gate.completed(succeeded=True)
    _append(root / "sol.jsonl", _FILL[torn:])

    assert gate.due(240.0)


def test_completed_partial_heartbeat_waits_for_threshold(tmp_path: Path) -> None:
    """Rescanning a torn tail does not turn a small heartbeat into an import."""
    root = _ledgers(tmp_path)
    gate = _imported(root, minimum=10**9)
    torn = len(_HEARTBEAT) // 2
    _append(root / "sol.jsonl", _HEARTBEAT + _HEARTBEAT[:torn])
    gate.submitted(120.0)
    gate.completed(succeeded=True)
    _append(root / "sol.jsonl", _HEARTBEAT[torn:])

    assert not gate.due(240.0)


@pytest.mark.parametrize(
    "content,expected",
    [
        (b"", 0),
        (b"torn", 0),
        (_HEARTBEAT, len(_HEARTBEAT)),
        (_HEARTBEAT + b"torn", len(_HEARTBEAT)),
        (_HEARTBEAT + b"x" * 40, len(_HEARTBEAT)),
    ],
)
def test_complete_prefix_stops_after_last_newline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: bytes,
    expected: int,
) -> None:
    """A torn tail longer than one bounded tail read is still walked back."""
    monkeypatch.setattr(gate_module, "_TAIL_SCAN_BYTES", 7)
    path = tmp_path / "sol.jsonl"
    path.write_bytes(content)

    assert gate_module._complete_prefix_size(path) == expected


def test_zero_threshold_imports_every_check(tmp_path: Path) -> None:
    """Operators can restore the former every-interval import cadence."""
    gate = _imported(_ledgers(tmp_path), minimum=0)

    assert gate.due(120.0)


@pytest.mark.parametrize(
    "minimum,age,error",
    [
        (-1, 600.0, "nonnegative integer"),
        (True, 600.0, "nonnegative integer"),
        (1.5, 600.0, "nonnegative integer"),
        (0, 0.0, "maximum age must be positive"),
        (0, float("nan"), "maximum age must be positive"),
    ],
)
def test_invalid_thresholds_are_rejected(
    tmp_path: Path, minimum: object, age: float, error: str
) -> None:
    """A misconfigured gate fails at construction rather than never importing."""
    with pytest.raises(ValueError, match=error):
        ResearchImportGate(
            tmp_path,
            minimum_pending_bytes=minimum,  # type: ignore[arg-type]
            maximum_age_seconds=age,
        )


def _controller(
    root: Path,
    calls: list[int],
    *,
    fail: bool = False,
    clock: list[datetime] | None = None,
    minimum_free_bytes: int = 0,
) -> BackgroundResearchSync:
    def sync(_database: Path, _ledger: Path) -> dict[str, object]:
        calls.append(len(calls))
        if fail:
            raise ResearchSyncError("database locked")
        return {"imported_events": 3}

    now = clock or [_AT]
    return BackgroundResearchSync(
        root.parent / "market.duckdb",
        root,
        120.0,
        sync,
        minimum_free_bytes=minimum_free_bytes,
        clock=lambda: now[0],
        import_gate=ResearchImportGate(
            root, minimum_pending_bytes=1024, maximum_age_seconds=600.0
        ),
    )


def _run(controller: BackgroundResearchSync, now: float) -> None:
    controller.poll(now=now)
    controller.wait_for_completion(timeout=2.0)
    controller.poll(now=now + 1.0)


def test_background_sync_skips_small_increments_without_new_attempt(
    tmp_path: Path,
) -> None:
    """A deferred import keeps ready telemetry and never touches DuckDB."""
    root = _ledgers(tmp_path)
    calls: list[int] = []
    clock = [_AT]
    controller = _controller(root, calls, clock=clock)
    try:
        _run(controller, 0.0)
        first = controller.telemetry.snapshot()
        _append(root / "decisions.jsonl", _HEARTBEAT)
        clock[0] = _AT + timedelta(seconds=120)
        controller.poll(now=120.0)
        deferred = controller.telemetry.snapshot()

        assert calls == [0]
        assert deferred["state"] == "ready"
        assert deferred["in_progress"] is False
        assert deferred["error"] is None
        assert deferred["last_attempt_at_utc"] == first["last_attempt_at_utc"]
        assert deferred["last_imported_events"] == 3
        assert deferred["last_success_age_seconds"] == 120.0
        assert set(deferred) == set(first)

        for now in (240.0, 360.0, 480.0):
            controller.poll(now=now)
        assert calls == [0]
        _run(controller, 600.0)
        assert calls == [0, 1]
    finally:
        controller.close()


def test_background_sync_imports_new_fill_at_next_interval(tmp_path: Path) -> None:
    """The archive stays fresh after a fill despite the byte threshold."""
    root = _ledgers(tmp_path)
    calls: list[int] = []
    controller = _controller(root, calls)
    try:
        _run(controller, 0.0)
        _append(root / "sol.jsonl", _FILL)
        controller.poll(now=119.0)
        assert calls == [0]
        _run(controller, 120.0)
        assert calls == [0, 1]
    finally:
        controller.close()


def test_background_sync_retries_failed_import_at_interval(tmp_path: Path) -> None:
    """Throttling never delays recovery from a failed import."""
    root = _ledgers(tmp_path)
    calls: list[int] = []
    controller = _controller(root, calls, fail=True)
    try:
        controller.poll(now=0.0)
        with pytest.raises(ResearchSyncError, match="database locked"):
            controller.wait_for_completion(timeout=2.0)
        controller.poll(now=1.0)
        assert controller.telemetry.snapshot()["state"] == "failed"
        controller.poll(now=121.0)
        with pytest.raises(ResearchSyncError, match="database locked"):
            controller.wait_for_completion(timeout=2.0)
        assert calls == [0, 1]
    finally:
        controller.close()


def test_deferral_rearms_no_later_than_maximum_age(tmp_path: Path) -> None:
    """Late polls cannot push the age-driven import past the maximum age."""
    root = _ledgers(tmp_path)
    calls: list[int] = []
    controller = _controller(root, calls)
    try:
        _run(controller, 0.0)
        _append(root / "decisions.jsonl", _HEARTBEAT)
        for now in (125.0, 250.0, 375.0, 500.0):
            controller.poll(now=now)
        assert calls == [0]

        _run(controller, 600.0)

        assert calls == [0, 1]
    finally:
        controller.close()


def test_disk_deferral_is_retried_at_next_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deferred telemetry clears within one interval once headroom returns."""
    root = _ledgers(tmp_path)
    calls: list[int] = []
    free = [64 * 1024**3]
    monkeypatch.setattr(
        "hypervector.research.cohort_background_sync.shutil.disk_usage",
        lambda _path: SimpleNamespace(free=free[0]),
    )
    controller = _controller(root, calls, minimum_free_bytes=8 * 1024**3)
    try:
        _run(controller, 0.0)
        _append(root / "decisions.jsonl", _HEARTBEAT)
        original = gate_module._ledger_sizes

        def unreadable(_root: Path) -> dict[Path, int]:
            raise OSError("ledger root briefly unavailable")

        monkeypatch.setattr(gate_module, "_ledger_sizes", unreadable)
        free[0] = 0
        controller.poll(now=120.0)
        assert controller.telemetry.snapshot()["state"] == "deferred"
        assert calls == [0]

        monkeypatch.setattr(gate_module, "_ledger_sizes", original)
        free[0] = 64 * 1024**3
        _run(controller, 240.0)

        assert calls == [0, 1]
        assert controller.telemetry.snapshot()["state"] == "ready"
    finally:
        controller.close()


def test_disk_deferral_keeps_pending_fill_due(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A headroom deferral never consumes the fill that made the check due."""
    root = _ledgers(tmp_path)
    calls: list[int] = []
    free = [64 * 1024**3]
    monkeypatch.setattr(
        "hypervector.research.cohort_background_sync.shutil.disk_usage",
        lambda _path: SimpleNamespace(free=free[0]),
    )
    controller = _controller(root, calls, minimum_free_bytes=8 * 1024**3)
    try:
        _run(controller, 0.0)
        _append(root / "sol.jsonl", _FILL)
        free[0] = 0
        controller.poll(now=120.0)
        assert calls == [0]
        free[0] = 64 * 1024**3
        _run(controller, 240.0)

        assert calls == [0, 1]
    finally:
        controller.close()
