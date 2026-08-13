"""Durable accepted-entry cadence state for staged cohort providers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.live.cohort_candidate_entry_clock import (
    AcceptedEntryClock,
    CandidateEntryClockStateError,
)

_STRATEGY = "btc_structural_continuation_fixed60_bidirectional_v1"
_SYMBOL = "BTC"


def test_clock_recovers_only_the_exact_candidate_and_symbol(tmp_path: Path) -> None:
    """Unrelated accepted actions cannot consume this candidate's cadence."""
    ledger = tmp_path / "decisions.jsonl"
    _write_rows(
        ledger,
        [
            _routing_row("other", _SYMBOL, "2026-08-04T20:00:00+00:00"),
            _routing_row(_STRATEGY, "HYPE", "2026-08-04T20:01:00+00:00"),
            _routing_row(_STRATEGY, _SYMBOL, "2026-08-04T20:02:00+00:00"),
        ],
    )

    clock = AcceptedEntryClock(ledger, strategy_id=_STRATEGY, symbol=_SYMBOL)

    assert clock.latest_ms == 1_785_873_720_000


def test_clock_incrementally_consumes_new_complete_rows(tmp_path: Path) -> None:
    """A later accepted entry updates state without rereading old rows."""
    ledger = tmp_path / "decisions.jsonl"
    _write_rows(
        ledger,
        [_routing_row(_STRATEGY, _SYMBOL, "2026-08-04T20:00:00+00:00")],
    )
    clock = AcceptedEntryClock(ledger, strategy_id=_STRATEGY, symbol=_SYMBOL)
    with ledger.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(_routing_row(_STRATEGY, _SYMBOL, "2026-08-04T21:15:00+00:00"))
            + "\n"
        )

    clock.refresh()

    assert clock.latest_ms == 1_785_878_100_000


def test_clock_rejects_an_incomplete_ledger_tail(tmp_path: Path) -> None:
    """Cadence recovery fails closed when the append boundary is ambiguous."""
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text('{"event_type":"intent_routing"', encoding="utf-8")

    with pytest.raises(CandidateEntryClockStateError, match="incomplete final row"):
        AcceptedEntryClock(ledger, strategy_id=_STRATEGY, symbol=_SYMBOL)


def _routing_row(strategy_id: str, symbol: str, observed: str) -> dict[str, object]:
    return {
        "event_type": "intent_routing",
        "observed_at_utc": observed,
        "payload": {
            "actions": [
                {
                    "action": "enter",
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                }
            ]
        },
    }


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
