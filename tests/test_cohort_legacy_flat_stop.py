"""Fail-closed tests for the legacy cohort's flat-boundary stop watcher."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.live import cohort_legacy_flat_stop as legacy_flat_stop
from hypervector.live.cohort_legacy_flat_stop import (
    LegacyFlatStopError,
    LegacyFlatStopEvidence,
    evaluate_legacy_flat_snapshot,
    watch_legacy_flat_boundary,
    write_legacy_stop_request,
)

_PROFILE = "c992cb2f958ed607d25d6be76a52a37070278061c0e8c186723dc574e6938f6b"
_RUN_ID = "bidirectional-live-1785826133777"
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")


def test_non_snapshot_record_is_ignored() -> None:
    """Intent and heartbeat rows cannot trigger a process stop."""
    row = _snapshot()
    row["event_type"] = "intent_routing"

    assert _evaluate(row) is None


def test_flat_snapshot_requires_exact_live_run_identity() -> None:
    """A different profile cannot satisfy the transition boundary."""
    row = _snapshot()
    row["profile_fingerprint"] = "a" * 64

    with pytest.raises(LegacyFlatStopError, match="profile fingerprint"):
        _evaluate(row)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("state", "OPEN", "not flat"),
        ("position_size_signed", 0.1, "nonzero position"),
        ("stop_oid", 123, "owned order"),
        ("last_fault", "boom", "fault"),
    ),
)
def test_flat_snapshot_rejects_lifecycle_or_order_residue(
    field: str,
    value: object,
    message: str,
) -> None:
    """Position, order, and fault residue all block a legacy stop."""
    row = _snapshot()
    assets = row["payload"]["assets"]
    assets[0][field] = value

    with pytest.raises(LegacyFlatStopError, match=message):
        _evaluate(row)


def test_exact_flat_snapshot_produces_auditable_evidence() -> None:
    """The exact current run may stop only after all four assets are clean."""
    evidence = _evaluate(_snapshot())

    assert evidence == LegacyFlatStopEvidence(
        run_id=_RUN_ID,
        profile_fingerprint=_PROFILE,
        observed_at_utc="2026-08-05T20:00:00+00:00",
        symbols=_SYMBOLS,
        source_sequence=70000,
    )


def test_stop_request_is_exclusive_and_preserves_evidence(tmp_path: Path) -> None:
    """An existing operator request cannot be overwritten or hidden."""
    stop = tmp_path / "STOP"
    evidence = _require_evidence(_evaluate(_snapshot()))

    write_legacy_stop_request(stop, evidence)

    payload = json.loads(stop.read_text(encoding="utf-8"))
    assert payload["reason"] == "legacy_flat_transition"
    assert payload["run_id"] == _RUN_ID
    assert payload["profile_fingerprint"] == _PROFILE
    with pytest.raises(LegacyFlatStopError, match="already exists"):
        write_legacy_stop_request(stop, evidence)


def test_watcher_starts_at_eof_and_stops_on_next_exact_flat_snapshot(
    tmp_path: Path,
) -> None:
    """Historical flat rows are ignored; only a newly appended row qualifies."""
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text(json.dumps(_snapshot()) + "\n", encoding="utf-8")
    appended = False

    def append_once(_: float) -> None:
        nonlocal appended
        if appended:
            return
        with ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_snapshot(sequence=70001)) + "\n")
        appended = True

    evidence = watch_legacy_flat_boundary(
        ledger,
        expected_profile_fingerprint=_PROFILE,
        expected_run_id=_RUN_ID,
        expected_symbols=_SYMBOLS,
        poll_seconds=0.01,
        timeout_seconds=1.0,
        sleep_fn=append_once,
    )

    assert evidence.source_sequence == 70001


def test_watcher_treats_open_snapshot_as_pending_until_flat(tmp_path: Path) -> None:
    """A protected open lifecycle keeps the watcher armed for a later flat row."""
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text(json.dumps(_snapshot()) + "\n", encoding="utf-8")
    appended = False

    def append_once(_: float) -> None:
        nonlocal appended
        if appended:
            return
        opened = _snapshot(sequence=70001)
        opened["payload"]["open_position_count"] = 1
        asset = opened["payload"]["assets"][3]
        asset["state"] = "OPEN"
        asset["position_size_signed"] = 0.44
        asset["entry_oid"] = 10
        asset["stop_oid"] = 11
        with ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(opened) + "\n")
            handle.write(json.dumps(_snapshot(sequence=70002)) + "\n")
        appended = True

    evidence = watch_legacy_flat_boundary(
        ledger,
        expected_profile_fingerprint=_PROFILE,
        expected_run_id=_RUN_ID,
        expected_symbols=_SYMBOLS,
        poll_seconds=0.01,
        timeout_seconds=1.0,
        sleep_fn=append_once,
    )

    assert evidence.source_sequence == 70002


def test_existing_final_snapshot_recovers_the_latest_exact_armed_run(
    tmp_path: Path,
) -> None:
    """A stopped cohort may recover its final strict flat snapshot without restart."""
    ledger = tmp_path / "decisions.jsonl"
    rows = [
        _configuration_identity(
            profile="d" * 64,
            run_id="bidirectional-observe-old",
            live_armed=False,
        ),
        _configuration_identity(),
        _snapshot(),
    ]
    ledger.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    loader = getattr(legacy_flat_stop, "load_existing_final_flat_boundary", None)
    assert callable(loader), "offline final-snapshot recovery is missing"

    evidence = loader(
        ledger,
        expected_profile_fingerprint=_PROFILE,
        expected_run_id=_RUN_ID,
        expected_symbols=_SYMBOLS,
    )

    assert evidence.source_sequence == 70000


def test_existing_final_snapshot_rejects_a_superseded_armed_run(
    tmp_path: Path,
) -> None:
    """Historical flat evidence cannot archive over a newer live identity."""
    ledger = tmp_path / "decisions.jsonl"
    rows = [
        _configuration_identity(),
        _snapshot(),
        _configuration_identity(
            profile="a" * 64,
            run_id="bidirectional-live-newer",
        ),
    ]
    ledger.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    loader = getattr(legacy_flat_stop, "load_existing_final_flat_boundary", None)
    assert callable(loader), "offline final-snapshot recovery is missing"

    with pytest.raises(LegacyFlatStopError, match="latest armed run identity"):
        loader(
            ledger,
            expected_profile_fingerprint=_PROFILE,
            expected_run_id=_RUN_ID,
            expected_symbols=_SYMBOLS,
        )


def _evaluate(row: dict[str, object]) -> LegacyFlatStopEvidence | None:
    return evaluate_legacy_flat_snapshot(
        row,
        expected_profile_fingerprint=_PROFILE,
        expected_run_id=_RUN_ID,
        expected_symbols=_SYMBOLS,
    )


def _require_evidence(
    value: LegacyFlatStopEvidence | None,
) -> LegacyFlatStopEvidence:
    if value is None:
        raise AssertionError("expected flat-stop evidence")
    return value


def _snapshot(*, sequence: int = 70000) -> dict[str, object]:
    return {
        "schema_version": 1,
        "sequence": sequence,
        "event_type": "cohort_snapshot",
        "observed_at_utc": "2026-08-05T20:00:00+00:00",
        "execution_mode": "live",
        "live_armed": True,
        "profile_fingerprint": _PROFILE,
        "run_id": _RUN_ID,
        "payload": {
            "open_position_count": 0,
            "assets": [
                {
                    "symbol": symbol,
                    "state": "FLAT",
                    "position_size_signed": 0.0,
                    "entry_oid": None,
                    "stop_oid": None,
                    "target_oid": None,
                    "last_fault": None,
                }
                for symbol in _SYMBOLS
            ],
        },
    }


def _configuration_identity(
    *,
    profile: str = _PROFILE,
    run_id: str = _RUN_ID,
    live_armed: bool = True,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "sequence": 69999,
        "event_type": "configuration_identity",
        "execution_mode": "live",
        "live_armed": live_armed,
        "profile_fingerprint": profile,
        "run_id": run_id,
    }
