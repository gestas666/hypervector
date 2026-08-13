"""Project normalized Hyperliquid events into paper-market telemetry."""

from __future__ import annotations

from hypervector.data.hl_events import L2SnapshotEvent
from hypervector.paper.book import BookLevel, BookSnapshot


def book_snapshot_from_event(event: L2SnapshotEvent) -> BookSnapshot:
    """Project one normalized L2 event without changing its venue timestamps."""
    return BookSnapshot(
        symbol=event.symbol,
        bids=tuple(BookLevel(level.price, level.size) for level in event.bids),
        asks=tuple(BookLevel(level.price, level.size) for level in event.asks),
        ts_recv_ms=event.received_ts_ns / 1_000_000,
        ts_exchange_ms=float(event.exchange_ts_ms),
        source=event.source,
    )
