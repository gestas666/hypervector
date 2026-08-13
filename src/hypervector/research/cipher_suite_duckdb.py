"""Read-only OHLCV extraction for causal Cipher suite research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd


_BAR_MINUTES = 5
CIPHER_RESEARCH_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_BARS_SQL = """
SELECT bar_open_at, open, high, low, close, volume
FROM canonical_trade_5m_bars
WHERE symbol = ? AND bar_open_at >= ? AND bar_open_at < ?
ORDER BY bar_open_at
"""


@dataclass(frozen=True)
class CipherOhlcvInputs:
    """Bounded five-minute OHLCV with causal warmup and outcome lookahead."""

    bars: pd.DataFrame
    query_start_utc: datetime
    query_end_utc: datetime


def load_cipher_ohlcv(
    database_path: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    *,
    history_bars: int,
    horizon_bars: int,
) -> CipherOhlcvInputs:
    """Load only the canonical bars required by the Cipher screen."""
    _validate_request(
        database_path, symbol, start_utc, end_utc, history_bars, horizon_bars
    )
    duration = timedelta(minutes=_BAR_MINUTES)
    query_start = start_utc - duration * history_bars
    query_end = end_utc + duration * horizon_bars
    with duckdb.connect(str(database_path), read_only=True) as connection:
        connection.execute("SET TimeZone='UTC'")
        _validate_schema(connection)
        bars = connection.execute(
            _BARS_SQL, [symbol.strip().upper(), query_start, query_end]
        ).df()
    bars["bar_open_at"] = pd.to_datetime(bars["bar_open_at"], utc=True)
    validate_cipher_ohlcv_coverage(bars, query_start, end_utc, horizon_bars)
    return CipherOhlcvInputs(bars, query_start, query_end)


def _validate_request(
    database_path: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    history_bars: int,
    horizon_bars: int,
) -> None:
    if not database_path.is_file():
        raise FileNotFoundError(f"research database does not exist: {database_path}")
    if symbol.strip().upper() not in CIPHER_RESEARCH_SYMBOLS:
        supported = ", ".join(CIPHER_RESEARCH_SYMBOLS)
        raise ValueError(f"Cipher symbol must be one of: {supported}")
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise ValueError("Cipher timestamps must be timezone-aware")
    if start_utc >= end_utc:
        raise ValueError("Cipher start must precede end")
    if history_bars < 200 or horizon_bars < 1:
        raise ValueError(
            "Cipher requires at least 200 warmup bars and positive lookahead"
        )


def _validate_schema(connection: duckdb.DuckDBPyConnection) -> None:
    tables = {str(row[0]) for row in connection.execute("SHOW TABLES").fetchall()}
    if "canonical_trade_5m_bars" not in tables:
        raise ValueError("missing required table: canonical_trade_5m_bars")
    columns = {
        str(row[0])
        for row in connection.execute("DESCRIBE canonical_trade_5m_bars").fetchall()
    }
    required = {"symbol", "bar_open_at", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(columns))
    if missing:
        raise ValueError(f"canonical_trade_5m_bars missing columns: {missing}")


def validate_cipher_ohlcv_coverage(
    bars: pd.DataFrame,
    query_start: datetime,
    signal_end: datetime,
    horizon_bars: int,
) -> None:
    """Require exact warmup and sufficient outcome lookahead coverage."""
    if bars.empty:
        raise ValueError("Cipher OHLCV query returned no bars")
    times = pd.DatetimeIndex(bars["bar_open_at"])
    if not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("Cipher OHLCV timestamps must be ordered and unique")
    if times[0] != pd.Timestamp(query_start):
        raise ValueError("Cipher feature warmup coverage is incomplete")
    required_last = pd.Timestamp(signal_end) + pd.Timedelta(
        minutes=_BAR_MINUTES * (horizon_bars - 1)
    )
    if times[-1] < required_last:
        raise ValueError("Cipher outcome lookahead coverage is incomplete")
