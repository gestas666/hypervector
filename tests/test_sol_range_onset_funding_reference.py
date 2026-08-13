"""Funding-reference regressions for the SOL range-onset shadow engine."""

from __future__ import annotations

import pytest

from hypervector.data.hl_events import AssetContextEvent, BookLevel, L2SnapshotEvent
from hypervector.research.range_onset_event_models import EventSignal
from hypervector.research.range_onset_forward_observer import (
    SharedCapitalSnapshot,
    SolRangeOnsetShadowEngine,
)


def _book(timestamp_ms: int) -> L2SnapshotEvent:
    return L2SnapshotEvent(
        symbol="SOL",
        exchange_ts_ms=timestamp_ms,
        received_ts_ns=timestamp_ms * 1_000_000,
        bids=(BookLevel(99.9, 40.0, 1),),
        asks=(BookLevel(100.1, 40.0, 1),),
    )


def _context(timestamp_ms: int) -> AssetContextEvent:
    return AssetContextEvent(
        symbol="SOL",
        observed_ts_ms=timestamp_ms,
        received_ts_ns=timestamp_ms * 1_000_000,
        mark_price=90.0,
        oracle_price=100.0,
        funding_rate_hourly=0.0001,
        open_interest=1_000_000.0,
        mid_price=95.0,
    )


def test_forward_funding_uses_oracle_price_not_mark_price() -> None:
    """Hyperliquid funding notional must be valued from the oracle price."""
    engine = SolRangeOnsetShadowEngine()
    engine.update_shared_capital(SharedCapitalSnapshot(3_590_000, 15_000.0, 0.0, "btc"))
    engine.ingest_decision(EventSignal(3_590_000, 100.0, True, False, False, False))
    engine.ingest_event(_book(3_590_100))
    position = engine.snapshot.position
    assert position is not None
    engine.drain_records()

    engine.ingest_event(_context(3_605_000))

    expected = -position.quantity * 100.0 * 0.0001
    updated = engine.snapshot.position
    assert updated is not None
    assert updated.funding_cashflow_usd == pytest.approx(expected)
    record = engine.drain_records()[0]
    assert record["funding_reference_price"] == pytest.approx(100.0)
    assert record["funding_reference_source"] == "hyperliquid_oracle_price"
