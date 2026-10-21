"""Durability and safety tests for the per-asset live event ledger."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.live.asset_ledger import (
    ASSET_LIVE_EVENT_TYPES,
    AssetLiveLedger,
    AssetLiveLedgerError,
)


def _ledger(path: Path, *, run_id: str = "run-001") -> AssetLiveLedger:
    return AssetLiveLedger(
        path=path,
        profile_id="fixture_asset_engine",
        profile_fingerprint="profile-hash",
        run_fingerprint="run-hash",
        run_id=run_id,
    )


def test_every_required_event_is_append_only_and_identity_stamped(
    tmp_path: Path,
) -> None:
    """All live evidence types share one authoritative live identity."""
    path = tmp_path / "data" / "live" / "bidirectional_cohort" / "sol.jsonl"
    ledger = _ledger(path)

    for index, event_type in enumerate(sorted(ASSET_LIVE_EVENT_TYPES), start=1):
        ledger.append(
            event_type=event_type,
            observed_at_utc=f"2026-07-31T12:{index:02d}:00+00:00",
            live_armed=True,
            execution_authority="hyperliquid_mainnet",
            payload={"event_index": index},
        )

    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(records) == len(ASSET_LIVE_EVENT_TYPES)
    assert [record["sequence"] for record in records] == list(
        range(1, len(records) + 1)
    )
    assert all(record["execution_mode"] == "live" for record in records)
    assert all(record["effective_mode"] == "LIVE ARMED" for record in records)
    assert all(
        record["profile_id"] == "fixture_asset_engine" for record in records
    )
    assert all(record["run_id"] == "run-001" for record in records)


def test_restart_continues_sequence_without_truncating_history(tmp_path: Path) -> None:
    """Reopening a ledger preserves prior evidence and advances sequence."""
    path = tmp_path / "data" / "live" / "bidirectional_cohort" / "sol.jsonl"
    _ledger(path).append(
        event_type="session_start",
        observed_at_utc="2026-07-31T12:00:00+00:00",
        live_armed=False,
        execution_authority="none",
        payload={"state": "PREFLIGHT"},
    )

    restarted = _ledger(path, run_id="run-002")
    restarted.append(
        event_type="effective_mode",
        observed_at_utc="2026-07-31T12:01:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"state": "FLAT"},
    )

    records = restarted.read_all()
    assert [record["sequence"] for record in records] == [1, 2]
    assert [record["run_id"] for record in records] == ["run-001", "run-002"]


def test_restart_sequence_recovery_does_not_materialize_complete_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Writer startup validates sequence without retaining every decoded row."""
    path = tmp_path / "data/live/bidirectional_cohort/sol.jsonl"
    first = _ledger(path)
    _append_heartbeat(first, minute=0)

    def forbidden_read_all(_self: AssetLiveLedger) -> list[dict[str, object]]:
        raise AssertionError("restart must not materialize complete history")

    monkeypatch.setattr(AssetLiveLedger, "read_all", forbidden_read_all)
    restarted = _ledger(path, run_id="run-002")

    assert restarted.end_cursor().next_sequence == 2


def test_matching_read_filters_without_materializing_complete_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recovery projections retain only selected rows during validation."""
    path = tmp_path / "data/live/bidirectional_cohort/sol.jsonl"
    ledger = _ledger(path)
    _append_heartbeat(ledger, minute=0)
    ledger.append(
        event_type="effective_mode",
        observed_at_utc="2026-07-31T12:01:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"state": "FLAT"},
    )

    def forbidden_read_all(_self: AssetLiveLedger) -> list[dict[str, object]]:
        raise AssertionError("filtered recovery must stream complete history")

    monkeypatch.setattr(AssetLiveLedger, "read_all", forbidden_read_all)
    records = ledger.read_matching(
        lambda record: record.get("event_type") == "effective_mode"
    )

    assert [record["sequence"] for record in records] == [2]


@pytest.mark.parametrize(
    "path",
    [
        Path("data/research/bidirectional_cohort/sol.jsonl"),
        Path("data/paper/bidirectional_cohort/sol.jsonl"),
        Path("data/live/other_strategy/decisions.jsonl"),
    ],
)
def test_live_ledger_refuses_wrong_storage_domains(path: Path) -> None:
    """Live evidence cannot be written into shadow, paper, or another strategy."""
    with pytest.raises(AssetLiveLedgerError, match="live/bidirectional_cohort"):
        _ledger(path)


def test_unknown_event_invalid_time_and_secret_shaped_payload_fail(
    tmp_path: Path,
) -> None:
    """Schema errors and secret-bearing data fail before any append."""
    path = tmp_path / "data" / "live" / "bidirectional_cohort" / "sol.jsonl"
    ledger = _ledger(path)

    with pytest.raises(AssetLiveLedgerError, match="event_type"):
        ledger.append(
            event_type="made_up_event",
            observed_at_utc="2026-07-31T12:00:00+00:00",
            live_armed=True,
            execution_authority="hyperliquid_mainnet",
            payload={},
        )
    with pytest.raises(AssetLiveLedgerError, match="UTC"):
        ledger.append(
            event_type="fault",
            observed_at_utc="2026-07-31T08:00:00-04:00",
            live_armed=True,
            execution_authority="hyperliquid_mainnet",
            payload={"reason": "test"},
        )
    with pytest.raises(AssetLiveLedgerError, match="secret"):
        ledger.append(
            event_type="fault",
            observed_at_utc="2026-07-31T12:00:00+00:00",
            live_armed=True,
            execution_authority="hyperliquid_mainnet",
            payload={"private_key": "must-not-write"},
        )
    assert not path.exists()


def test_corrupt_existing_line_refuses_restart_append(tmp_path: Path) -> None:
    """A damaged ledger cannot be silently treated as an empty history."""
    path = tmp_path / "data" / "live" / "bidirectional_cohort" / "sol.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(AssetLiveLedgerError, match="line 1"):
        _ledger(path)


def test_shared_cohort_ledgers_are_valid_live_domains(tmp_path: Path) -> None:
    """One cohort ledger and symbol sidecars share the strict live schema."""
    root = tmp_path / "data/live/bidirectional_cohort"
    for name in ("decisions.jsonl", "btc.jsonl", "eth.jsonl"):
        ledger = _ledger(root / name)
        ledger.append(
            event_type="cohort_snapshot",
            observed_at_utc="2026-08-01T12:00:00+00:00",
            live_armed=True,
            execution_authority="hyperliquid_mainnet",
            payload={"symbol": "BTC"},
        )
        assert ledger.read_all()[0]["event_type"] == "cohort_snapshot"


def test_observer_ledger_uses_a_separate_domain_and_truthful_mode(
    tmp_path: Path,
) -> None:
    """A disarmed observer cannot masquerade as live telemetry."""
    path = tmp_path / "data/observe/btc_hype_breakout_transfer/decisions.jsonl"
    ledger = AssetLiveLedger(
        path=path,
        profile_id="fixture_btc_hype_breakout_transfer",
        profile_fingerprint="profile-hash",
        run_fingerprint="run-hash",
        run_id="observer-001",
        execution_mode="observe",
    )

    ledger.append(
        event_type="heartbeat",
        observed_at_utc="2026-08-05T17:30:00+00:00",
        live_armed=False,
        execution_authority="none",
        payload={"status": "running"},
    )

    record = ledger.read_all()[0]
    assert record["execution_mode"] == "observe"
    assert record["effective_mode"] == "OBSERVE ONLY"
    with pytest.raises(AssetLiveLedgerError, match="cannot be armed"):
        ledger.append(
            event_type="heartbeat",
            observed_at_utc="2026-08-05T17:31:00+00:00",
            live_armed=True,
            execution_authority="hyperliquid_mainnet",
            payload={"status": "running"},
        )


def test_cursor_reads_only_rows_appended_by_the_active_writer(tmp_path: Path) -> None:
    """Incremental telemetry receives the exact suffix once and in sequence."""
    path = tmp_path / "data/live/bidirectional_cohort/sol.jsonl"
    ledger = _ledger(path)
    _append_heartbeat(ledger, minute=0)
    cursor = ledger.end_cursor()
    _append_heartbeat(ledger, minute=1)

    rows, advanced = ledger.read_from_cursor(cursor)

    assert [row["sequence"] for row in rows] == [2]
    assert ledger.read_from_cursor(advanced) == ([], advanced)


def test_cursor_rejects_an_incomplete_appended_row(tmp_path: Path) -> None:
    """A torn suffix cannot be ignored or represented as fresh telemetry."""
    path = tmp_path / "data/live/bidirectional_cohort/sol.jsonl"
    ledger = _ledger(path)
    _append_heartbeat(ledger, minute=0)
    cursor = ledger.end_cursor()
    with path.open("ab") as handle:
        handle.write(b'{"sequence":2')

    with pytest.raises(AssetLiveLedgerError, match="incomplete row"):
        ledger.read_from_cursor(cursor)


def test_cursor_rejects_a_second_writer_on_the_same_path(tmp_path: Path) -> None:
    """A runtime cursor fails closed when another ledger instance appends."""
    path = tmp_path / "data/live/bidirectional_cohort/sol.jsonl"
    ledger = _ledger(path)
    _append_heartbeat(ledger, minute=0)
    cursor = ledger.end_cursor()
    _append_heartbeat(_ledger(path, run_id="run-002"), minute=1)

    with pytest.raises(AssetLiveLedgerError, match="outside its active writer"):
        ledger.read_from_cursor(cursor)


def _append_heartbeat(ledger: AssetLiveLedger, *, minute: int) -> None:
    ledger.append(
        event_type="heartbeat",
        observed_at_utc=f"2026-07-31T12:{minute:02d}:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"status": "running"},
    )
