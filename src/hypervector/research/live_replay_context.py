"""Causal mark, oracle, and funding context from live Hyperliquid evidence."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from hypervector.data.oxa_api import validate_symbol, validate_window
from hypervector.research.maker_replay_context import MakerReplayContext


def database_live_replay_context(
    database_path: Path,
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    maximum_price_gap_seconds: float = 5.0,
    maximum_funding_age_seconds: float = 5.0,
) -> tuple[MakerReplayContext, dict[str, object]]:
    """Load validated backward-known live mark, oracle, and funding context."""
    validate_symbol(symbol)
    validate_window(start, end)
    if not database_path.is_file():
        raise FileNotFoundError(f"research database is missing: {database_path}")
    if maximum_price_gap_seconds <= 0.0 or maximum_funding_age_seconds <= 0.0:
        raise ValueError("live context gap limits must be positive")
    with duckdb.connect(str(database_path), read_only=True) as connection:
        connection.execute("SET TimeZone = 'UTC'")
        prices = _price_rows(connection, symbol, start, end)
    _validate_price_coverage(prices, start, end, maximum_price_gap_seconds)
    funding = _funding_rows(
        prices, start, end, maximum_age_seconds=maximum_funding_age_seconds
    )
    context = MakerReplayContext(
        prices.loc[:, ["ts_ms", "mark_price", "oracle_price"]], funding
    )
    coverage = _coverage(prices, funding, database_path)
    return context, coverage


def _price_rows(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    return connection.execute(
        """
        WITH deduplicated AS (
            SELECT observed_ts_ms, received_ts_ns, mark_price, oracle_price,
                   funding_rate_hourly, file_id
            FROM live_asset_contexts
            WHERE symbol = ?
            QUALIFY row_number() OVER (
                PARTITION BY symbol, observed_ts_ms
                ORDER BY received_ts_ns DESC, file_id DESC
            ) = 1
        ), preceding AS (
            SELECT observed_ts_ms ts_ms, mark_price, oracle_price,
                   funding_rate_hourly
            FROM deduplicated
            WHERE observed_ts_ms <= epoch_ms(?)
            ORDER BY observed_ts_ms DESC LIMIT 1
        ), active AS (
            SELECT observed_ts_ms ts_ms, mark_price, oracle_price,
                   funding_rate_hourly
            FROM deduplicated
            WHERE observed_ts_ms > epoch_ms(?)
              AND observed_ts_ms < epoch_ms(?)
        )
        SELECT * FROM preceding UNION ALL SELECT * FROM active ORDER BY ts_ms
        """,
        [symbol, start, start, end],
    ).fetchdf()


def _validate_price_coverage(
    prices: pd.DataFrame,
    start: datetime,
    end: datetime,
    maximum_gap_seconds: float,
) -> None:
    if prices.empty:
        raise ValueError("live price context does not cover the requested window")
    maximum_ms = maximum_gap_seconds * 1000.0
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    first_ms, last_ms = int(prices.ts_ms.iloc[0]), int(prices.ts_ms.iloc[-1])
    if first_ms > start_ms or start_ms - first_ms > maximum_ms:
        raise ValueError("live price context does not cover the requested start")
    if end_ms - last_ms > maximum_ms:
        raise ValueError("live price context does not cover the requested end")
    gaps = prices.ts_ms.diff().dropna()
    if not gaps.empty and float(gaps.max()) > maximum_ms:
        raise ValueError("live price context exceeds the maximum permitted gap")


def _funding_rows(
    prices: pd.DataFrame,
    start: datetime,
    end: datetime,
    *,
    maximum_age_seconds: float,
) -> pd.DataFrame:
    boundaries = _funding_boundaries(start, end)
    if boundaries.empty:
        return pd.DataFrame(columns=["event_ts_ms", "funding_rate"])
    observations = prices.loc[:, ["ts_ms", "funding_rate_hourly"]].sort_values("ts_ms")
    aligned = pd.merge_asof(
        boundaries, observations, left_on="event_ts_ms", right_on="ts_ms"
    )
    ages = aligned.event_ts_ms - aligned.ts_ms
    if aligned.ts_ms.isna().any() or (ages > maximum_age_seconds * 1000.0).any():
        raise ValueError("live funding observation is stale at an hourly boundary")
    return aligned.loc[:, ["event_ts_ms", "funding_rate_hourly"]].rename(
        columns={"funding_rate_hourly": "funding_rate"}
    )


def _funding_boundaries(start: datetime, end: datetime) -> pd.DataFrame:
    first = pd.Timestamp(start).ceil("1h")
    if first <= pd.Timestamp(start):
        first += pd.Timedelta(hours=1)
    stamps = pd.date_range(first, pd.Timestamp(end), freq="1h", inclusive="left")
    return pd.DataFrame(
        {"event_ts_ms": [int(stamp.timestamp() * 1000) for stamp in stamps]}
    )


def _coverage(
    prices: pd.DataFrame,
    funding: pd.DataFrame,
    database_path: Path,
) -> dict[str, object]:
    gaps = prices.ts_ms.diff().dropna() / 1000.0
    return {
        "data_source": "duckdb_live_asset_context",
        "database_path": str(database_path.resolve()),
        "price_rows": len(prices),
        "maximum_price_gap_seconds": float(gaps.max()) if len(gaps) else 0.0,
        "funding_source": "live_active_asset_context_backward",
        "funding_rows": len(funding),
        "checksums_verified_on_import": True,
    }
