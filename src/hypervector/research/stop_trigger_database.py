"""Public-trade stop-crossing bounds from canonical venue evidence."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import duckdb

from hypervector.data.oxa_api import validate_symbol

Direction = Literal["long", "short"]


@dataclass(frozen=True)
class TradeStopCrossing:
    """First public trade observed beyond one stop boundary."""

    trade_id: int
    timestamp_ms: int
    price: float


def first_trade_stop_crossing(
    connection: duckdb.DuckDBPyConnection,
    *,
    symbol: str,
    direction: Direction,
    stop_price: float,
    start_time_ms: int,
    end_time_ms: int,
) -> TradeStopCrossing | None:
    """Return the first adverse trade in a half-open event-time window."""
    normalized = symbol.strip().upper()
    validate_symbol(normalized)
    _validate_contract(direction, stop_price, start_time_ms, end_time_ms)
    comparator = "<=" if direction == "long" else ">="
    row = connection.execute(
        f"""
        WITH ranked_window AS (
            SELECT
                trades.trade_id,
                trades.ts_exchange_ms,
                trades.price,
                row_number() OVER (
                    PARTITION BY trades.symbol, trades.trade_id
                    ORDER BY bundles.start_utc DESC
                ) AS ordinal
            FROM public_trades AS trades
            INNER JOIN archive_bundles AS bundles USING (bundle_id)
            WHERE trades.symbol = ?
              AND trades.ts_exchange_ms >= ?
              AND trades.ts_exchange_ms < ?
        )
        SELECT trade_id, ts_exchange_ms, price
        FROM ranked_window
        WHERE ordinal = 1
          AND price {comparator} ?
        ORDER BY ts_exchange_ms, trade_id
        LIMIT 1
        """,
        [normalized, start_time_ms, end_time_ms, stop_price],
    ).fetchone()
    if row is None:
        return None
    return TradeStopCrossing(
        _integer(row[0], "trade_id"),
        _integer(row[1], "trade timestamp"),
        _positive_number(row[2], "trade price"),
    )


def _validate_contract(
    direction: object,
    stop_price: float,
    start_time_ms: int,
    end_time_ms: int,
) -> None:
    if direction not in ("long", "short"):
        raise ValueError("direction must be long or short")
    _positive_number(stop_price, "stop_price")
    _nonnegative_integer(start_time_ms, "start_time_ms")
    _nonnegative_integer(end_time_ms, "end_time_ms")
    if end_time_ms <= start_time_ms:
        raise ValueError("end_time_ms must follow start_time_ms")


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be positive and finite")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return number


def _nonnegative_integer(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"{label} must be an integer")
    return value
