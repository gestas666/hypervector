"""Timestamp-bounded visible-depth execution from the research database."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from hypervector.data.oxa_api import MarketFamily, validate_market_symbol
from hypervector.research.market_depth_fill import (
    MarketDepthFill,
    MarketSide,
    depth_levels_from_records,
    walk_market_order,
)

DEFAULT_MAXIMUM_BOOK_DELAY_MS = 15_000


@dataclass(frozen=True)
class TimedMarketDepthFill:
    """One market fill tied to its causal book snapshot and latency."""

    event_time_ms: int
    snapshot_time_ms: int
    latency_ms: int
    fill: MarketDepthFill


def market_fill_at_or_after(
    connection: duckdb.DuckDBPyConnection,
    *,
    symbol: str,
    event_time_ms: int,
    side: MarketSide,
    quantity: float,
    maximum_delay_ms: int = DEFAULT_MAXIMUM_BOOK_DELAY_MS,
    market_family: MarketFamily = "core",
) -> TimedMarketDepthFill:
    """Walk the first recorded L2 snapshot inside a strict latency window."""
    normalized = _market_symbol(symbol, market_family)
    _validate_time_bounds(event_time_ms, maximum_delay_ms)
    row = connection.execute(
        """
        SELECT ts_exchange_ms, bids, asks
        FROM replay_book_snapshots
        WHERE symbol = ?
          AND ts_exchange_ms >= ?
          AND ts_exchange_ms <= ?
        ORDER BY ts_exchange_ms
        LIMIT 1
        """,
        [normalized, event_time_ms, event_time_ms + maximum_delay_ms],
    ).fetchone()
    if row is None:
        raise LookupError(
            f"no {normalized} book snapshot within {maximum_delay_ms}ms "
            f"after {event_time_ms}"
        )
    snapshot_ms = _integer(row[0], "book timestamp")
    bids = depth_levels_from_records(row[1], label="bids")
    asks = depth_levels_from_records(row[2], label="asks")
    levels = asks if side == "buy" else bids
    fill = walk_market_order(levels, side=side, quantity=quantity)
    return TimedMarketDepthFill(
        event_time_ms,
        snapshot_ms,
        snapshot_ms - event_time_ms,
        fill,
    )


def _market_symbol(symbol: str, market_family: MarketFamily) -> str:
    stripped = symbol.strip()
    normalized = stripped.upper() if market_family == "core" else stripped
    validate_market_symbol(normalized, market_family)
    return normalized


def _validate_time_bounds(event_time_ms: int, maximum_delay_ms: int) -> None:
    if isinstance(event_time_ms, bool) or not isinstance(event_time_ms, int):
        raise ValueError("event_time_ms must be a non-negative integer")
    if event_time_ms < 0:
        raise ValueError("event_time_ms must be a non-negative integer")
    if isinstance(maximum_delay_ms, bool) or not isinstance(maximum_delay_ms, int):
        raise ValueError("maximum_delay_ms must be a positive integer")
    if maximum_delay_ms <= 0:
        raise ValueError("maximum_delay_ms must be a positive integer")


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"{label} must be an integer")
    return value
