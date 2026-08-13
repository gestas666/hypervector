"""Read-only DuckDB inputs for venue-native one-minute impulse research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd


_REQUIRED_RELATIONS = frozenset(
    {"canonical_trade_1m_bars", "replay_public_trades", "replay_book_snapshots"}
)
_BARS_SQL = """
SELECT bar_open_at, open, high, low, close, volume, trade_count
FROM canonical_trade_1m_bars
WHERE symbol = ? AND bar_open_at >= ? AND bar_open_at < ?
ORDER BY bar_open_at
"""
_TRADES_SQL = """
SELECT
    time_bucket(INTERVAL '1 minute', ts_utc) AS bar_open_at,
    coalesce(sum(size) FILTER (WHERE lower(aggressor_side) = 'buy'), 0.0)
        AS buy_volume,
    coalesce(sum(size) FILTER (WHERE lower(aggressor_side) = 'sell'), 0.0)
        AS sell_volume
FROM replay_public_trades
WHERE symbol = ? AND ts_utc >= ? AND ts_utc < ?
GROUP BY bar_open_at
ORDER BY bar_open_at
"""
_BOOKS_SQL = """
WITH bucketed AS (
    SELECT *, time_bucket(INTERVAL '1 minute', ts_utc) AS bar_open_at
    FROM replay_book_snapshots
    WHERE symbol = ? AND ts_utc >= ? AND ts_utc < ?
)
SELECT
    bar_open_at,
    max(ts_utc) AS last_book_at,
    arg_max(imbalance_5, ts_exchange_ms) AS imbalance_5_last,
    arg_max(imbalance_5, ts_exchange_ms)
        - arg_min(imbalance_5, ts_exchange_ms) AS imbalance_5_delta,
    (arg_max(micro_price, ts_exchange_ms) / arg_max(mid_price, ts_exchange_ms)
        - 1.0) * 10000.0 AS micro_price_delta_bps,
    arg_max(spread_bps, ts_exchange_ms) AS spread_bps_last,
    arg_max(bid_depth_10, ts_exchange_ms) AS bid_depth_10_last,
    arg_max(ask_depth_10, ts_exchange_ms) AS ask_depth_10_last
FROM bucketed
GROUP BY bar_open_at
ORDER BY bar_open_at
"""


@dataclass(frozen=True)
class OrderFlowImpulseInputs:
    """Causal one-minute price, public-trade, and L2 frames."""

    bars: pd.DataFrame
    trades: pd.DataFrame
    books: pd.DataFrame
    query_start_utc: datetime
    query_end_utc: datetime


def load_orderflow_impulse_inputs(
    database_path: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    *,
    warmup_minutes: int,
    horizon_minutes: int,
) -> OrderFlowImpulseInputs:
    """Load a bounded research interval with warmup and label lookahead."""
    normalized = _validate_request(
        database_path, symbol, start_utc, end_utc, warmup_minutes, horizon_minutes
    )
    query_start = start_utc - timedelta(minutes=warmup_minutes)
    query_end = end_utc + timedelta(minutes=horizon_minutes)
    parameters = [normalized, query_start, query_end]
    with duckdb.connect(str(database_path), read_only=True) as connection:
        connection.execute("SET TimeZone='UTC'")
        _validate_schema(connection)
        bars = connection.execute(_BARS_SQL, parameters).df()
        trades = connection.execute(_TRADES_SQL, parameters).df()
        books = connection.execute(_BOOKS_SQL, parameters).df()
    _normalize_times(bars, "bar_open_at")
    _normalize_times(trades, "bar_open_at")
    _normalize_times(books, "bar_open_at")
    _normalize_times(books, "last_book_at")
    if bars.empty:
        raise ValueError("order-flow impulse query returned no price bars")
    trades = _align_trade_minutes(bars, trades)
    return OrderFlowImpulseInputs(bars, trades, books, query_start, query_end)


def audit_orderflow_coverage(
    database_path: Path, symbols: tuple[str, ...]
) -> pd.DataFrame:
    """Report archive book and trade coverage without filling missing assets."""
    if not database_path.is_file():
        raise FileNotFoundError(f"research database does not exist: {database_path}")
    if not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("coverage symbols must be non-empty and unique")
    records: list[dict[str, object]] = []
    with duckdb.connect(str(database_path), read_only=True) as connection:
        _validate_schema(connection)
        for symbol in symbols:
            records.append(_coverage_row(connection, symbol.strip().upper()))
    return pd.DataFrame(records)


def _coverage_row(
    connection: duckdb.DuckDBPyConnection, symbol: str
) -> dict[str, object]:
    book = connection.execute(
        "SELECT count(*), min(ts_utc), max(ts_utc) "
        "FROM replay_book_snapshots WHERE symbol = ?",
        [symbol],
    ).fetchone()
    trade = connection.execute(
        "SELECT count(*), min(ts_utc), max(ts_utc) "
        "FROM replay_public_trades WHERE symbol = ?",
        [symbol],
    ).fetchone()
    if book is None or trade is None:
        raise RuntimeError("coverage aggregation returned no row")
    return {
        "symbol": symbol,
        "book_rows": int(book[0]),
        "book_first_utc": book[1],
        "book_last_utc": book[2],
        "trade_rows": int(trade[0]),
        "trade_first_utc": trade[1],
        "trade_last_utc": trade[2],
    }


def _validate_request(
    database_path: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    warmup_minutes: int,
    horizon_minutes: int,
) -> str:
    if not database_path.is_file():
        raise FileNotFoundError(f"research database does not exist: {database_path}")
    normalized = symbol.strip().upper()
    if normalized not in {"BTC", "SOL"}:
        raise ValueError("order-flow impulse history supports only BTC or SOL")
    if start_utc.tzinfo is None or end_utc.tzinfo is None or start_utc >= end_utc:
        raise ValueError("order-flow impulse bounds must be ordered and timezone-aware")
    if warmup_minutes <= 0 or horizon_minutes <= 0:
        raise ValueError("warmup and horizon minutes must be positive")
    return normalized


def _validate_schema(connection: duckdb.DuckDBPyConnection) -> None:
    observed = {str(row[0]) for row in connection.execute("SHOW TABLES").fetchall()}
    missing = sorted(_REQUIRED_RELATIONS.difference(observed))
    if missing:
        raise ValueError(f"order-flow research database missing relations: {missing}")


def _align_trade_minutes(bars: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    identities = bars.loc[:, ["bar_open_at"]]
    aligned = identities.merge(
        trades, on="bar_open_at", how="left", validate="one_to_one"
    )
    aligned[["buy_volume", "sell_volume"]] = aligned[
        ["buy_volume", "sell_volume"]
    ].fillna(0.0)
    return aligned


def _normalize_times(frame: pd.DataFrame, column: str) -> None:
    if column in frame:
        frame[column] = pd.to_datetime(frame[column], utc=True)
