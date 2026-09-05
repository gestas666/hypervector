"""Exact bounded trade-bar and L2 inputs for EMA-speed research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


_TRADE_SQL = """
SELECT
    time_bucket(INTERVAL '15 minutes', bar_open_at) AS bar_open_at,
    arg_min(open, bar_open_at) AS open,
    max(high) AS high,
    min(low) AS low,
    arg_max(close, bar_open_at) AS close,
    count(DISTINCT bar_open_at) AS trade_child_count,
    min(bar_open_at) AS first_child_at,
    max(bar_open_at) AS last_child_at
FROM canonical_trade_5m_bars
WHERE symbol = ? AND bar_open_at >= ? AND bar_open_at < ?
GROUP BY 1
ORDER BY 1
"""

_BOOK_SQL = """
WITH bucketed AS (
    SELECT
        time_bucket(INTERVAL '15 minutes', ts_utc) AS bar_open_at,
        ts_exchange_ms,
        ts_utc,
        best_bid,
        best_ask
    FROM replay_book_snapshots
    WHERE symbol = ? AND ts_utc >= ? AND ts_utc < ?
), ordered AS (
    SELECT *, ts_exchange_ms - lag(ts_exchange_ms) OVER (
        PARTITION BY bar_open_at ORDER BY ts_exchange_ms, best_bid, best_ask
    ) AS snapshot_interval_ms
    FROM bucketed
)
SELECT
    bar_open_at,
    arg_min(best_bid, struct_pack(ts := ts_exchange_ms, bid := best_bid,
        ask := best_ask)) AS entry_bid,
    arg_min(best_ask, struct_pack(ts := ts_exchange_ms, bid := best_bid,
        ask := best_ask)) AS entry_ask,
    arg_max(best_bid, struct_pack(ts := ts_exchange_ms, bid := best_bid,
        ask := best_ask)) AS close_bid,
    arg_max(best_ask, struct_pack(ts := ts_exchange_ms, bid := best_bid,
        ask := best_ask)) AS close_ask,
    min(best_bid) AS risk_low,
    max(best_ask) AS risk_high,
    count(*) AS source_snapshot_count,
    date_diff('millisecond', bar_open_at, min(ts_utc)) AS first_boundary_delay_ms,
    date_diff('millisecond', max(ts_utc),
        bar_open_at + INTERVAL '15 minutes') AS end_boundary_age_ms,
    coalesce(max(snapshot_interval_ms), 0) AS maximum_snapshot_interval_ms
FROM ordered
GROUP BY 1
ORDER BY 1
"""


@dataclass(frozen=True)
class EmaSpeedInputs:
    """One exact common-cadence market frame and its requested bounds."""

    bars: pd.DataFrame
    start_utc: datetime
    end_utc: datetime


def load_ema_speed_inputs(
    database_path: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
) -> EmaSpeedInputs:
    """Load complete 15-minute trade bars and exact next-boundary BBO evidence."""
    normalized = _validate_request(database_path, symbol, start_utc, end_utc)
    parameters = [normalized, start_utc, end_utc]
    with duckdb.connect(str(database_path), read_only=True) as connection:
        connection.execute("SET TimeZone='UTC'")
        _validate_relations(connection)
        trades = connection.execute(_TRADE_SQL, parameters).df()
        books = connection.execute(_BOOK_SQL, parameters).df()
    frame = _common_frame(trades, books, start_utc, end_utc)
    return EmaSpeedInputs(frame, start_utc, end_utc)


def _validate_request(
    database_path: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
) -> str:
    if not database_path.is_file():
        raise FileNotFoundError(f"EMA-speed database does not exist: {database_path}")
    normalized = symbol.strip().upper()
    if normalized not in {"BTC", "SOL"}:
        raise ValueError("EMA-speed symbol must be BTC or SOL")
    if start_utc.tzinfo is None or end_utc.tzinfo is None or start_utc >= end_utc:
        raise ValueError("EMA-speed bounds must be ordered and timezone-aware")
    for value in (start_utc, end_utc):
        if value.minute % 15 or value.second or value.microsecond:
            raise ValueError("EMA-speed bounds must align to 15-minute boundaries")
    return normalized


def _validate_relations(connection: duckdb.DuckDBPyConnection) -> None:
    required = {"canonical_trade_5m_bars", "replay_book_snapshots"}
    observed = {str(row[0]) for row in connection.execute("SHOW TABLES").fetchall()}
    missing = sorted(required.difference(observed))
    if missing:
        raise ValueError(f"EMA-speed database missing relations: {missing}")


def _common_frame(
    trades: pd.DataFrame,
    books: pd.DataFrame,
    start_utc: datetime,
    end_utc: datetime,
) -> pd.DataFrame:
    _normalize_index(trades)
    _normalize_index(books)
    index = pd.date_range(start_utc, end_utc, freq="15min", inclusive="left")
    frame = pd.DataFrame(index=index).join(trades).join(books)
    frame["trade_child_count"] = frame["trade_child_count"].fillna(0).astype(int)
    frame["source_snapshot_count"] = (
        frame["source_snapshot_count"].fillna(0).astype(int)
    )
    frame["source_complete"] = _complete_trade_source(frame)
    frame["l2_path_complete"] = _complete_l2_path(frame)
    return frame


def _complete_trade_source(frame: pd.DataFrame) -> pd.Series:
    expected_first = frame.index.to_series(index=frame.index)
    expected_last = expected_first + pd.Timedelta(minutes=10)
    return (
        frame["trade_child_count"].eq(3)
        & pd.to_datetime(frame["first_child_at"], utc=True).eq(expected_first)
        & pd.to_datetime(frame["last_child_at"], utc=True).eq(expected_last)
    )


def _complete_l2_path(frame: pd.DataFrame) -> pd.Series:
    numeric = frame[
        [
            "entry_bid",
            "entry_ask",
            "close_bid",
            "close_ask",
            "risk_low",
            "risk_high",
            "first_boundary_delay_ms",
            "end_boundary_age_ms",
            "maximum_snapshot_interval_ms",
        ]
    ].astype(float)
    finite = pd.Series(np.isfinite(numeric).all(axis=1), index=frame.index)
    quotes = numeric["entry_bid"].gt(0.0) & numeric["entry_ask"].ge(
        numeric["entry_bid"]
    )
    timing = (
        numeric[
            [
                "first_boundary_delay_ms",
                "end_boundary_age_ms",
                "maximum_snapshot_interval_ms",
            ]
        ]
        .le(15_000.0)
        .all(axis=1)
    )
    return finite & quotes & frame["source_snapshot_count"].ge(2) & timing


def _normalize_index(frame: pd.DataFrame) -> None:
    if "bar_open_at" not in frame:
        raise ValueError("EMA-speed query result lacks bar_open_at")
    frame["bar_open_at"] = pd.to_datetime(frame["bar_open_at"], utc=True)
    frame.set_index("bar_open_at", inplace=True)
