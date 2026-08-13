"""Read-only market and funding inputs for flow-exhaustion research."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from hypervector.research.low_tf_duckdb import LowTimeframeInputFrames
from hypervector.research.market_cipher_data import load_verified_hourly_funding


_FINAL_FLOW_COLUMNS = frozenset({"final_60_buy_volume", "final_60_sell_volume"})
_BOOK_COLUMNS = ("bar_open_at", "last_book_at", "imbalance_5_last")
_MINUTES_SQL = """
SELECT
    bar_open_at AS timestamp,
    open,
    high,
    low,
    close
FROM canonical_trade_1m_bars
WHERE symbol = ? AND bar_open_at >= ? AND bar_open_at < ?
ORDER BY bar_open_at
"""


def assemble_flow_exhaustion_rows(
    inputs: LowTimeframeInputFrames,
) -> pd.DataFrame:
    """Merge complete five-minute bars and flow with optional same-bar L2."""
    missing = sorted(_FINAL_FLOW_COLUMNS.difference(inputs.trades.columns))
    if missing:
        raise ValueError(f"flow-exhaustion trade inputs missing: {missing}")
    bars = inputs.bars.copy()
    rows = bars.merge(
        inputs.trades,
        on="bar_open_at",
        how="inner",
        validate="one_to_one",
    )
    if len(rows) != len(bars):
        raise ValueError("flow-exhaustion flow rows do not cover every price bar")
    books = inputs.books.loc[:, list(_BOOK_COLUMNS)].copy()
    return rows.merge(
        books,
        on="bar_open_at",
        how="left",
        validate="one_to_one",
    )


def load_flow_exhaustion_minute_path(
    database_path: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    funding_paths: list[Path],
) -> pd.DataFrame:
    """Load exact one-minute prices with verified hourly funding events."""
    _validate_request(database_path, symbol, start_utc, end_utc)
    with duckdb.connect(str(database_path), read_only=True) as connection:
        connection.execute("SET TimeZone='UTC'")
        _validate_relation(connection)
        rows = connection.execute(
            _MINUTES_SQL,
            [symbol.strip().upper(), start_utc, end_utc],
        ).df()
    if rows.empty:
        raise ValueError("flow-exhaustion minute query returned no rows")
    rows["timestamp"] = pd.to_datetime(rows["timestamp"], utc=True)
    funding = load_verified_hourly_funding(
        funding_paths,
        pd.Timestamp(start_utc),
        pd.Timestamp(end_utc),
    )
    rows["funding_rate"] = rows["timestamp"].map(funding).fillna(0.0)
    return rows


def _validate_request(
    database_path: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
) -> None:
    if not database_path.is_file():
        raise FileNotFoundError(f"research database does not exist: {database_path}")
    if symbol.strip().upper() not in {"BTC", "SOL"}:
        raise ValueError("flow-exhaustion minute symbol must be BTC or SOL")
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise ValueError("flow-exhaustion minute bounds must be timezone-aware")
    if start_utc >= end_utc:
        raise ValueError("flow-exhaustion minute start must precede end")


def _validate_relation(connection: duckdb.DuckDBPyConnection) -> None:
    relations = {str(row[0]) for row in connection.execute("SHOW TABLES").fetchall()}
    if "canonical_trade_1m_bars" not in relations:
        raise ValueError("missing required table: canonical_trade_1m_bars")
    expected = {"symbol", "bar_open_at", "open", "high", "low", "close"}
    columns = {
        str(row[0])
        for row in connection.execute("DESCRIBE canonical_trade_1m_bars").fetchall()
    }
    missing = sorted(expected.difference(columns))
    if missing:
        raise ValueError(f"canonical_trade_1m_bars missing columns: {missing}")
