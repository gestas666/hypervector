"""Recovery must stay bounded and atomic across append-only ledger failures."""

from __future__ import annotations

from pathlib import Path
import tracemalloc

import pytest

from hypervector.live.cohort_candidate_entry_clock import (
    AcceptedEntryClock,
    CandidateEntryClockStateError,
)


def test_recovery_memory_does_not_scale_with_ledger_size(tmp_path: Path) -> None:
    """A large ledger should allocate at most a small streaming buffer."""
    ledger = tmp_path / "ledger.jsonl"
    row = b'{"event_type":"telemetry","padding":"' + b"x" * 900 + b'"}\n'
    with ledger.open("wb") as stream:
        for _ in range(12_000):
            stream.write(row)
    tracemalloc.start()
    try:
        clock = AcceptedEntryClock(ledger, strategy_id="test", symbol="BTC")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert clock.latest_ms is None
    assert peak < 1_000_000


@pytest.mark.parametrize("tail", [b'{"event_type":', b"\xff\n", b"[]\n", b"bad\n"])
def test_failed_refresh_does_not_publish_partial_recovery(
    tmp_path: Path, tail: bytes
) -> None:
    """A corrupt append cannot change the previously accepted recovery state."""
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(b'{"event_type":"telemetry"}\n')
    clock = AcceptedEntryClock(ledger, strategy_id="test", symbol="BTC")
    offset = ledger.stat().st_size
    accepted = (
        b'{"event_type":"intent_routing","observed_at_utc":"2026-01-01T00:00:00Z",'
        b'"payload":{"actions":[{"action":"enter","strategy_id":"test","symbol":"BTC"}]}}\n'
    )
    with ledger.open("ab") as stream:
        stream.write(accepted + tail)
    with pytest.raises(CandidateEntryClockStateError):
        clock.refresh()
    assert clock.latest_ms is None
    assert clock._offset == offset


def test_truncated_ledger_is_rejected(tmp_path: Path) -> None:
    """Streaming preserves the original fail-closed truncation boundary."""
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(b'{"event_type":"telemetry"}\n')
    clock = AcceptedEntryClock(ledger, strategy_id="test", symbol="BTC")
    ledger.write_bytes(b"")
    with pytest.raises(CandidateEntryClockStateError, match="truncated"):
        clock.refresh()


@pytest.mark.parametrize("strategy,symbol", [("", "BTC"), ("test", " ")])
def test_empty_identity_is_a_technical_error(strategy: str, symbol: str) -> None:
    """Recovery cannot match an unspecified provider or venue identity."""
    with pytest.raises(ValueError, match="non-empty"):
        AcceptedEntryClock(None, strategy_id=strategy, symbol=symbol)


@pytest.mark.parametrize("payload", [None, {"actions": None}, {"actions": [None]}])
def test_malformed_routing_cannot_be_treated_as_no_entry(
    tmp_path: Path, payload: object
) -> None:
    """Invalid routing evidence is different from an explicit no-entry result."""
    import json

    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        json.dumps({"event_type": "intent_routing", "payload": payload}) + "\n"
    )
    with pytest.raises(CandidateEntryClockStateError):
        AcceptedEntryClock(ledger, strategy_id="test", symbol="BTC")


@pytest.mark.parametrize("observed", [None, "bad", "2026-01-01T00:00:00"])
def test_accepted_entry_requires_a_valid_aware_timestamp(
    tmp_path: Path, observed: object
) -> None:
    """An accepted entry without usable cadence evidence must fail recovery."""
    import json

    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        json.dumps(
            {
                "event_type": "intent_routing",
                "observed_at_utc": observed,
                "payload": {
                    "actions": [
                        {"action": "enter", "strategy_id": "test", "symbol": "BTC"}
                    ]
                },
            }
        )
        + "\n"
    )
    with pytest.raises(CandidateEntryClockStateError):
        AcceptedEntryClock(ledger, strategy_id="test", symbol="BTC")


def test_truncation_during_an_open_read_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A captured nonempty prefix cannot be accepted after its bytes disappear."""
    from io import BytesIO

    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(b'{"event_type":"telemetry"}\n')
    monkeypatch.setattr(Path, "open", lambda *_a, **_k: BytesIO())
    with pytest.raises(CandidateEntryClockStateError, match="truncated"):
        AcceptedEntryClock(ledger, strategy_id="test", symbol="BTC")
