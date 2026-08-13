"""Read-only DuckDB extraction for causal low-timeframe research inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd


REQUIRED_RELATIONS: frozenset[str] = frozenset(
    {
        "replay_public_trades",
        "replay_book_snapshots",
    }
)
_BAR_MINUTES = 5
_BARS_SQL = """
SELECT
    time_bucket(INTERVAL '5 minutes', ts_utc) AS bar_open_at,
    first(price ORDER BY ts_exchange_ms, trade_id) AS open,
    max(price) AS high,
    min(price) AS low,
    last(price ORDER BY ts_exchange_ms, trade_id) AS close,
    CAST(sum(CAST(size AS DECIMAL(38, 18))) AS DOUBLE) AS volume,
    count(*) AS trade_count
FROM replay_public_trades
WHERE symbol = ? AND ts_utc >= ? AND ts_utc < ?
GROUP BY time_bucket(INTERVAL '5 minutes', ts_utc)
ORDER BY bar_open_at
"""
_TRADES_SQL = """
SELECT
    time_bucket(INTERVAL '5 minutes', ts_utc) AS bar_open_at,
    coalesce(CAST(sum(CAST(size AS DECIMAL(38, 18))) FILTER (
        WHERE lower(aggressor_side) = 'buy'
    ) AS DOUBLE), 0.0) AS buy_volume,
    coalesce(CAST(sum(CAST(size AS DECIMAL(38, 18))) FILTER (
        WHERE lower(aggressor_side) = 'sell'
    ) AS DOUBLE), 0.0) AS sell_volume,
    coalesce(CAST(sum(CAST(size AS DECIMAL(38, 18))) FILTER (
        WHERE lower(aggressor_side) = 'buy'
          AND ts_utc >= time_bucket(INTERVAL '5 minutes', ts_utc)
              + INTERVAL 4 MINUTES
    ) AS DOUBLE), 0.0) AS final_60_buy_volume,
    coalesce(CAST(sum(CAST(size AS DECIMAL(38, 18))) FILTER (
        WHERE lower(aggressor_side) = 'sell'
          AND ts_utc >= time_bucket(INTERVAL '5 minutes', ts_utc)
              + INTERVAL 4 MINUTES
    ) AS DOUBLE), 0.0) AS final_60_sell_volume
FROM replay_public_trades
WHERE symbol = ? AND ts_utc >= ? AND ts_utc < ?
GROUP BY time_bucket(INTERVAL '5 minutes', ts_utc)
ORDER BY bar_open_at
"""
_BOOKS_SQL = """
WITH bucketed AS (
    SELECT
        *,
        time_bucket(INTERVAL '5 minutes', ts_utc) AS bar_open_at
    FROM replay_book_snapshots
    WHERE symbol = ? AND ts_utc >= ? AND ts_utc < ?
)
SELECT
    bar_open_at,
    max(ts_utc) AS last_book_at,
    arg_max(imbalance_5, ts_exchange_ms) AS imbalance_5_last,
    avg(imbalance_5) FILTER (
        WHERE ts_utc >= bar_open_at + INTERVAL 4 MINUTES
    ) AS imbalance_5_mean_60s,
    arg_max(imbalance_5, ts_exchange_ms) FILTER (
        WHERE ts_utc >= bar_open_at + INTERVAL 4 MINUTES
    ) - arg_min(imbalance_5, ts_exchange_ms) FILTER (
        WHERE ts_utc >= bar_open_at + INTERVAL 4 MINUTES
    ) AS imbalance_5_delta_60s,
    arg_max(imbalance_10, ts_exchange_ms) AS imbalance_10_last,
    arg_max(spread_bps, ts_exchange_ms) AS spread_bps_last,
    (
        arg_max(micro_price, ts_exchange_ms)
        / arg_max(mid_price, ts_exchange_ms) - 1.0
    ) * 10000.0 AS micro_price_delta_bps,
    arg_max(bid_depth_10, ts_exchange_ms) AS bid_depth_10_last,
    arg_max(ask_depth_10, ts_exchange_ms) AS ask_depth_10_last
FROM bucketed
GROUP BY bar_open_at
ORDER BY bar_open_at
"""


@dataclass(frozen=True)
class LowTimeframeInputFrames:
    """Preaggregated price, public-trade, and L2 rows for one symbol."""

    bars: pd.DataFrame
    trades: pd.DataFrame
    books: pd.DataFrame
    query_start_utc: datetime
    query_end_utc: datetime
    missing_book_bars: int
    orphan_book_bars: int


def load_low_timeframe_inputs(
    database_path: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    *,
    history_bars: int = 36,
    horizon_bars: int = 12,
) -> LowTimeframeInputFrames:
    """Load a bounded window with feature warmup and outcome lookahead."""
    _validate_request(database_path, symbol, start_utc, end_utc)
    query_start = start_utc - timedelta(minutes=_BAR_MINUTES * history_bars)
    query_end = end_utc + timedelta(minutes=_BAR_MINUTES * horizon_bars)
    with duckdb.connect(str(database_path), read_only=True) as connection:
        _configure_connection(connection)
        _validate_schema(connection)
        parameters = [symbol.strip().upper(), query_start, query_end]
        bars = connection.execute(_BARS_SQL, parameters).df()
        trades = connection.execute(_TRADES_SQL, parameters).df()
        books = connection.execute(_BOOKS_SQL, parameters).df()
    _normalize_timestamps(bars, "bar_open_at")
    _normalize_timestamps(trades, "bar_open_at")
    _normalize_timestamps(books, "bar_open_at")
    _normalize_timestamps(books, "last_book_at")
    missing_book_bars, orphan_book_bars = _validate_coverage(
        bars, trades, books, query_start, end_utc
    )
    book_is_candle_aligned = books["bar_open_at"].isin(bars["bar_open_at"])
    books = books.loc[book_is_candle_aligned].reset_index(drop=True)
    return LowTimeframeInputFrames(
        bars=bars,
        trades=trades,
        books=books,
        query_start_utc=query_start,
        query_end_utc=query_end,
        missing_book_bars=missing_book_bars,
        orphan_book_bars=orphan_book_bars,
    )


def _configure_connection(connection: duckdb.DuckDBPyConnection) -> None:
    """Pin the session timezone and suppress nondiagnostic progress output."""
    connection.execute("SET TimeZone='UTC'")
    connection.execute("SET enable_progress_bar=false")


def _validate_request(
    database_path: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
) -> None:
    if not database_path.is_file():
        raise FileNotFoundError(f"research database does not exist: {database_path}")
    if symbol.strip().upper() not in {"BTC", "SOL"}:
        raise ValueError("low-timeframe challenger symbol must be BTC or SOL")
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise ValueError("challenger timestamps must be timezone-aware")
    if start_utc >= end_utc:
        raise ValueError("challenger start must precede end")


def _validate_schema(connection: duckdb.DuckDBPyConnection) -> None:
    observed = {str(row[0]) for row in connection.execute("SHOW TABLES").fetchall()}
    missing = sorted(REQUIRED_RELATIONS.difference(observed))
    if missing:
        raise ValueError(f"missing required tables: {missing}")
    required_columns = {
        "replay_public_trades": {
            "symbol",
            "trade_id",
            "ts_exchange_ms",
            "ts_utc",
            "aggressor_side",
            "price",
            "size",
        },
        "replay_book_snapshots": {
            "symbol",
            "ts_exchange_ms",
            "ts_utc",
            "bid_depth_10",
            "ask_depth_10",
            "imbalance_5",
            "imbalance_10",
            "mid_price",
            "micro_price",
            "spread_bps",
        },
    }
    for relation, expected in required_columns.items():
        columns = {
            str(row[0]) for row in connection.execute(f"DESCRIBE {relation}").fetchall()
        }
        absent = sorted(expected.difference(columns))
        if absent:
            raise ValueError(f"{relation} missing required columns: {absent}")


def _normalize_timestamps(frame: pd.DataFrame, column: str) -> None:
    if column not in frame:
        return
    frame[column] = pd.to_datetime(frame[column], utc=True)


def _validate_coverage(
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    books: pd.DataFrame,
    query_start: datetime,
    signal_end: datetime,
) -> tuple[int, int]:
    if bars.empty or trades.empty or books.empty:
        raise ValueError("challenger query returned an empty market input")
    expected = pd.DatetimeIndex(bars["bar_open_at"])
    observed_trades = pd.DatetimeIndex(trades["bar_open_at"])
    if not expected.equals(observed_trades):
        raise ValueError("trades coverage does not align with five-minute bars")
    observed_books = pd.DatetimeIndex(books["bar_open_at"])
    if expected[0] > pd.Timestamp(query_start):
        raise ValueError("challenger feature warmup coverage is incomplete")
    if expected[-1] < pd.Timestamp(signal_end):
        raise ValueError("challenger outcome horizon coverage is incomplete")
    missing_books = len(expected.difference(observed_books))
    orphan_books = len(observed_books.difference(expected))
    return missing_books, orphan_books
