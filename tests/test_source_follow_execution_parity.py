"""Production event-runtime replay contracts for source-follow lifecycles."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent, PublicTradeEvent
from hypervector.research.source_follow_execution_parity import (
    SourceLifecycleSpec,
    replay_source_lifecycle,
)


def _book(timestamp_ms: int, *, bid_size: float, ask_size: float) -> L2SnapshotEvent:
    return L2SnapshotEvent(
        symbol="BTC",
        exchange_ts_ms=timestamp_ms,
        received_ts_ns=timestamp_ms * 1_000_000,
        bids=(BookLevel(100.0, bid_size, 1),),
        asks=(BookLevel(101.0, ask_size, 1),),
    )


def _trade(
    timestamp_ms: int,
    trade_id: int,
    *,
    side: Literal["buy", "sell"],
    price: float,
    size: float,
) -> PublicTradeEvent:
    return PublicTradeEvent(
        symbol="BTC",
        aggressor_side=side,
        price=price,
        size=size,
        transaction_hash=f"0x{trade_id}",
        exchange_ts_ms=timestamp_ms,
        received_ts_ns=timestamp_ms * 1_000_000,
        trade_id=trade_id,
        buyer="buyer",
        seller="seller",
    )


def test_replay_consumes_displayed_queue_before_entry_and_target_fill() -> None:
    """Production parity must retain displayed queue and partial-fill friction."""
    signal_time = "2026-07-24T13:20:00+00:00"
    start = int(datetime.fromisoformat(signal_time).timestamp() * 1_000)
    events = (
        _book(start, bid_size=2.0, ask_size=2.0),
        _book(start + 100, bid_size=2.0, ask_size=2.0),
        _trade(start + 101, 1, side="buy", price=102.0, size=2.0),
        _trade(start + 102, 2, side="buy", price=102.0, size=1.0),
        _book(start + 200, bid_size=2.0, ask_size=2.0),
        _trade(start + 201, 3, side="sell", price=99.0, size=2.0),
        _trade(start + 202, 4, side="sell", price=99.0, size=1.0),
    )
    spec = SourceLifecycleSpec(
        signal_time_utc=signal_time,
        direction="short",
        quantity=1.0,
        target_price_fraction=1.0 / 101.0,
    )

    result = replay_source_lifecycle(events, spec)

    assert result.status == "completed"
    assert result.entry_first_at == "2026-07-24T13:20:00.102000+00:00"
    assert result.entry_filled_quantity == 1.0
    assert result.entry_fill_count == 1
    assert result.exit_completed_at == "2026-07-24T13:20:00.202000+00:00"
    assert result.exit_filled_quantity == 1.0
    assert result.exit_fill_count == 1


def test_replay_retains_runtime_six_second_book_freshness() -> None:
    """Lifecycle replay must use the shadow profile's six-second event age."""
    signal_time = "2026-07-24T13:20:00+00:00"
    start = int(datetime.fromisoformat(signal_time).timestamp() * 1_000)
    events = (
        _book(start, bid_size=2.0, ask_size=2.0),
        _trade(start + 4_000, 1, side="buy", price=102.0, size=3.0),
    )
    spec = SourceLifecycleSpec(
        signal_time_utc=signal_time,
        direction="short",
        quantity=1.0,
    )

    result = replay_source_lifecycle(events, spec)

    assert result.status == "open"
    assert result.entry_filled_quantity == 1.0
