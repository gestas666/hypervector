"""Normalized production-event access for canonical Hyperliquid archives."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

import duckdb

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent, PublicTradeEvent

ArchiveEvent = L2SnapshotEvent | PublicTradeEvent


def archive_book_rows(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
    start: datetime,
    end: datetime,
) -> list[tuple[object, ...]]:
    """Load canonical full-depth rows for one bounded window."""
    return connection.execute(
        """
        SELECT ts_exchange_ms, bids, asks, source
        FROM replay_book_snapshots
        WHERE symbol = ?
          AND ts_exchange_ms >= epoch_ms(?)
          AND ts_exchange_ms < epoch_ms(?)
        ORDER BY ts_exchange_ms
        """,
        [symbol, start, end],
    ).fetchall()


def archive_trade_rows(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
    start: datetime,
    end: datetime,
) -> list[tuple[object, ...]]:
    """Load deduplicated public trades for one bounded window."""
    return connection.execute(
        """
        SELECT trades.ts_exchange_ms, trades.trade_id,
               trades.aggressor_side, trades.price, trades.size, trades.source
        FROM public_trades AS trades
        INNER JOIN archive_bundles AS bundles USING (bundle_id)
        WHERE trades.symbol = ?
          AND trades.ts_exchange_ms >= epoch_ms(?)
          AND trades.ts_exchange_ms < epoch_ms(?)
        QUALIFY row_number() OVER (
            PARTITION BY trades.symbol, trades.trade_id
            ORDER BY bundles.start_utc DESC
        ) = 1
        ORDER BY ts_exchange_ms, trade_id
        """,
        [symbol, start, end],
    ).fetchall()


def live_book_rows(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
    start: datetime,
    end: datetime,
) -> list[tuple[object, ...]]:
    """Load deduplicated full-depth rows from the live recorder."""
    return connection.execute(
        """
        SELECT exchange_ts_ms, received_ts_ns, bids, asks, source
        FROM replay_live_book_snapshots
        WHERE symbol = ? AND exchange_ts_ms >= epoch_ms(?)
          AND exchange_ts_ms < epoch_ms(?)
        ORDER BY exchange_ts_ms, received_ts_ns
        """,
        [symbol, start, end],
    ).fetchall()


def live_trade_rows(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
    start: datetime,
    end: datetime,
) -> list[tuple[object, ...]]:
    """Load deduplicated public trades from the live recorder."""
    return connection.execute(
        """
        SELECT exchange_ts_ms, received_ts_ns, trade_id, aggressor_side,
               price, size, transaction_hash, buyer, seller, source
        FROM replay_live_public_trades
        WHERE symbol = ? AND exchange_ts_ms >= epoch_ms(?)
          AND exchange_ts_ms < epoch_ms(?)
        ORDER BY exchange_ts_ms, trade_id
        """,
        [symbol, start, end],
    ).fetchall()


def archive_book_event(symbol: str, row: tuple[object, ...]) -> L2SnapshotEvent:
    """Normalize one canonical full-depth row for production matching."""
    timestamp, bids, asks, source = row
    timestamp_ms = int(cast(int, timestamp))
    return L2SnapshotEvent(
        symbol=symbol,
        exchange_ts_ms=timestamp_ms,
        received_ts_ns=timestamp_ms * 1_000_000,
        bids=_levels(bids),
        asks=_levels(asks),
        source=str(source),
    )


def live_book_event(symbol: str, row: tuple[object, ...]) -> L2SnapshotEvent:
    """Normalize one live book while preserving its receive timestamp."""
    timestamp, received, bids, asks, source = row
    return L2SnapshotEvent(
        symbol=symbol,
        exchange_ts_ms=int(cast(int, timestamp)),
        received_ts_ns=int(cast(int, received)),
        bids=_levels(bids),
        asks=_levels(asks),
        source=str(source),
    )


def archive_trade_event(symbol: str, row: tuple[object, ...]) -> PublicTradeEvent:
    """Normalize one canonical public trade for production matching."""
    timestamp, trade_id, side, price, size, source = row
    timestamp_ms = int(cast(int, timestamp))
    identity = int(cast(int, trade_id))
    return PublicTradeEvent(
        symbol=symbol,
        aggressor_side=cast(Literal["buy", "sell"], str(side)),
        price=float(cast(float, price)),
        size=float(cast(float, size)),
        transaction_hash=f"archive-{timestamp_ms}-{identity}",
        exchange_ts_ms=timestamp_ms,
        received_ts_ns=timestamp_ms * 1_000_000,
        trade_id=identity,
        buyer="archive-buyer",
        seller="archive-seller",
        source=str(source),
    )


def live_trade_event(symbol: str, row: tuple[object, ...]) -> PublicTradeEvent:
    """Normalize one live trade while preserving recorder identity fields."""
    timestamp, received, trade_id, side, price, size, tx, buyer, seller, source = row
    return PublicTradeEvent(
        symbol=symbol,
        aggressor_side=cast(Literal["buy", "sell"], str(side)),
        price=float(cast(float, price)),
        size=float(cast(float, size)),
        transaction_hash=str(tx),
        exchange_ts_ms=int(cast(int, timestamp)),
        received_ts_ns=int(cast(int, received)),
        trade_id=int(cast(int, trade_id)),
        buyer=str(buyer),
        seller=str(seller),
        source=str(source),
    )


def archive_event_sort_key(event: ArchiveEvent) -> tuple[int, int, int]:
    """Return stable book-before-trade ordering at equal timestamps."""
    priority = 2 if isinstance(event, L2SnapshotEvent) else 3
    identity = event.trade_id if isinstance(event, PublicTradeEvent) else 0
    return event.exchange_ts_ms, priority, identity


def _levels(value: object) -> tuple[BookLevel, ...]:
    if not isinstance(value, list):
        raise ValueError("archive book levels must be a list")
    return tuple(
        BookLevel(float(level["px"]), float(level["sz"]), int(level["n"]))
        for level in value
        if isinstance(level, dict)
    )
