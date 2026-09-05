"""Causal source-boundary tests for HIP-3 lifecycle commands."""

from __future__ import annotations

import pytest

from hypervector.research.hip3_shadow_command_sources import (
    bounded_books,
    bounded_decisions,
)


def _book(received_ms: object) -> dict[str, object]:
    return {
        "event_type": "book_observation",
        "payload": {"recv_ts_ms": received_ms},
    }


def test_bounded_books_selects_only_causal_book_observations() -> None:
    """Mixed live-ledger state rows must not be parsed as order books."""
    rows = [
        {"event_type": "position", "payload": {"size_signed": 0.0}},
        _book(1_000),
        {"event_type": "reconciliation", "payload": {"fill_ids": []}},
        _book(2_001),
    ]

    assert bounded_books(rows, 2_000) == (_book(1_000),)


def test_bounded_books_rejects_malformed_book_observation() -> None:
    """An explicit book row with an invalid receipt cannot be skipped."""
    with pytest.raises(ValueError, match="book receipt"):
        bounded_books([_book("1000")], 2_000)


def test_bounded_books_rejects_untyped_payload_input() -> None:
    """An untyped payload cannot silently become exact book evidence."""
    with pytest.raises(ValueError, match="no books"):
        bounded_books([{"payload": {"recv_ts_ms": 1_000}}], 2_000)


def test_bounded_decisions_keeps_only_the_frozen_prospective_epoch() -> None:
    """Earlier journal epochs cannot be compared with a later candle ledger."""
    rows = [_decision(900, 950), _decision(1_800, 1_850), _decision(2_700, 3_100)]

    bounded, start_ms = bounded_decisions(
        rows,
        observed_at=3_000,
        interval_ms=900,
        decision_start_ms=1_800,
    )

    assert bounded == (_decision(1_800, 1_850),)
    assert start_ms == 900


def _decision(decision_ms: int, observed_ms: int) -> dict[str, object]:
    return {
        "decision": {
            "decision_time_ms": decision_ms,
            "observed_at_ms": observed_ms,
        }
    }
