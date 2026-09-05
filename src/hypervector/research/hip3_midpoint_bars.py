"""Causal midpoint OHLC bars from verified HIP-3 L2 archives."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path

import duckdb
import pandas as pd

from hypervector.data.oxa_api import validate_hip3_symbol

_REQUIRED_RELATIONS = frozenset(
    {"archive_bundles", "archive_bundle_provenance", "replay_book_snapshots"}
)


@dataclass(frozen=True)
class Hip3MidpointBars:
    """Verified archive coverage and non-interpolated midpoint bars."""

    symbol: str
    archive_start_utc: pd.Timestamp
    archive_end_utc: pd.Timestamp
    archive_bundles: int
    archive_book_rows: int
    expected_bar_count: int
    missing_bar_count: int
    bars: pd.DataFrame
    execution_authority: str = "none"


def build_hip3_midpoint_bars(
    database_path: Path,
    *,
    symbol: str,
    bar_minutes: int = 15,
    start_utc: pd.Timestamp | None = None,
    end_utc: pd.Timestamp | None = None,
) -> Hip3MidpointBars:
    """Build causal bars from one exact, provenance-complete HIP-3 archive."""
    _validate_request(database_path, symbol, bar_minutes)
    with duckdb.connect(str(database_path), read_only=True) as connection:
        connection.execute("SET TimeZone='UTC'")
        _validate_schema(connection)
        bounds = _requested_bounds(connection, symbol, start_utc, end_utc)
        archive = _archive_metadata(connection, symbol, bounds[0], bounds[1])
        bars = _load_bars(connection, symbol, archive[0], archive[1], bar_minutes)
    expected = _expected_bar_count(archive[0], archive[1], bar_minutes)
    return Hip3MidpointBars(
        symbol=symbol,
        archive_start_utc=archive[0],
        archive_end_utc=archive[1],
        archive_bundles=archive[2],
        archive_book_rows=archive[3],
        expected_bar_count=expected,
        missing_bar_count=max(expected - len(bars), 0),
        bars=bars,
    )


def _validate_request(database_path: Path, symbol: str, bar_minutes: int) -> None:
    if not database_path.is_file():
        raise FileNotFoundError(
            f"HIP-3 research database does not exist: {database_path}"
        )
    validate_hip3_symbol(symbol)
    if isinstance(bar_minutes, bool) or not isinstance(bar_minutes, int):
        raise ValueError("bar_minutes must be a positive integer")
    if bar_minutes <= 0 or 60 % bar_minutes:
        raise ValueError("bar_minutes must be a positive divisor of 60")


def _validate_schema(connection: duckdb.DuckDBPyConnection) -> None:
    observed = {str(row[0]) for row in connection.execute("SHOW TABLES").fetchall()}
    missing = sorted(_REQUIRED_RELATIONS.difference(observed))
    if missing:
        raise ValueError(f"HIP-3 midpoint database is missing relations: {missing}")


def _archive_metadata(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
) -> tuple[pd.Timestamp, pd.Timestamp, int, int]:
    row = connection.execute(
        """
        WITH scoped AS (
            SELECT b.*, p.market_family, p.book_only,
                   min(b.book_rows) OVER source_hour AS minimum_book_rows,
                   max(b.book_rows) OVER source_hour AS maximum_book_rows,
                   row_number() OVER (
                       source_hour ORDER BY p.book_only ASC, b.bundle_id
                   ) AS source_priority
            FROM archive_bundles AS b
            LEFT JOIN archive_bundle_provenance AS p USING (bundle_id)
            WHERE b.symbol = ? AND b.start_utc >= ? AND b.end_utc <= ?
            WINDOW source_hour AS (PARTITION BY b.symbol, b.start_utc, b.end_utc)
        ), canonical AS (
            SELECT * FROM scoped WHERE source_priority = 1
        )
        SELECT min(start_utc), max(end_utc), count(*), sum(book_rows),
               count(*) FILTER (WHERE market_family = 'hip3'),
               (SELECT count(*) FROM scoped),
               (SELECT count(*) FILTER (WHERE market_family = 'hip3') FROM scoped),
               max(CASE WHEN minimum_book_rows != maximum_book_rows THEN 1 ELSE 0 END)
        FROM canonical
        """,
        [symbol, start_utc, end_utc],
    ).fetchone()
    if (
        row is None
        or row[0] is None
        or _utc(row[0]) != start_utc
        or _utc(row[1]) != end_utc
        or int(row[2]) != int(row[4])
        or int(row[5]) != int(row[6])
        or int(row[7]) != 0
    ):
        raise ValueError(f"{symbol} does not have complete HIP-3 provenance")
    return _utc(row[0]), _utc(row[1]), int(row[2]), int(row[3])


def _requested_bounds(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
    start_utc: pd.Timestamp | None,
    end_utc: pd.Timestamp | None,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    if (start_utc is None) != (end_utc is None):
        raise ValueError(
            "HIP-3 midpoint start_utc and end_utc must be supplied together"
        )
    if start_utc is None:
        row = connection.execute(
            "SELECT min(start_utc), max(end_utc) FROM archive_bundles WHERE symbol = ?",
            [symbol],
        ).fetchone()
        if row is None or row[0] is None or row[1] is None:
            raise ValueError(f"{symbol} has no archive bundle coverage")
        return _utc(row[0]), _utc(row[1])
    start, end = _utc(start_utc), _utc(end_utc)
    if start >= end:
        raise ValueError("HIP-3 midpoint bounds must be ordered")
    return start, end


def _load_bars(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
    bar_minutes: int,
) -> pd.DataFrame:
    interval = f"INTERVAL '{bar_minutes} minutes'"
    frame = connection.execute(
        f"""
        WITH observed AS (
            SELECT *, time_bucket({interval}, ts_utc) AS bar_open_at,
                   ts_exchange_ms - lag(ts_exchange_ms) OVER (
                       PARTITION BY time_bucket({interval}, ts_utc)
                       ORDER BY ts_exchange_ms
                   ) AS snapshot_interval_ms
            FROM replay_book_snapshots
            WHERE symbol = ? AND ts_utc >= ? AND ts_utc < ?
        )
        SELECT bar_open_at,
               arg_min(mid_price, ts_exchange_ms) AS open,
               max(mid_price) AS high,
               min(mid_price) AS low,
               arg_max(mid_price, ts_exchange_ms) AS close,
               arg_min(best_bid, ts_exchange_ms) AS entry_bid,
               arg_min(best_ask, ts_exchange_ms) AS entry_ask,
               arg_max(best_bid, ts_exchange_ms) AS decision_bid,
               arg_max(best_ask, ts_exchange_ms) AS decision_ask,
               arg_max(micro_price, ts_exchange_ms) AS decision_micro_price,
               arg_max(spread_bps, ts_exchange_ms) AS decision_spread_bps,
               arg_max(imbalance_5, ts_exchange_ms) AS decision_imbalance_5,
               arg_max(imbalance_10, ts_exchange_ms) AS decision_imbalance_10,
               count(*) AS source_snapshot_count,
               min(ts_exchange_ms)
                   - epoch_ms(bar_open_at)
                   AS first_boundary_delay_ms,
               epoch_ms(bar_open_at + {interval})
                   - max(ts_exchange_ms) AS end_boundary_age_ms
               ,coalesce(max(snapshot_interval_ms), 0)
                   AS maximum_snapshot_interval_ms
        FROM observed
        GROUP BY 1
        ORDER BY 1
        """,
        [symbol, start_utc, end_utc],
    ).df()
    if frame.empty:
        raise ValueError(f"{symbol} archive contains no midpoint snapshots")
    frame["bar_open_at"] = pd.to_datetime(frame["bar_open_at"], utc=True)
    output = frame.set_index("bar_open_at")
    complete = output.index + pd.Timedelta(minutes=bar_minutes) <= end_utc
    output = output.loc[complete].copy()
    if output.empty:
        raise ValueError(f"{symbol} archive contains no completed midpoint bars")
    _validate_bars(output)
    output["gap_before_bars"] = _gap_before(output.index, bar_minutes)
    output["source"] = "0xarchive_hyperliquid_hip3_l2_midpoint"
    return output


def _validate_bars(bars: pd.DataFrame) -> None:
    if not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError("HIP-3 midpoint bars must be ordered and unique")
    for column in ("open", "high", "low", "close"):
        values = bars[column].astype(float)
        if not values.map(isfinite).all() or values.le(0.0).any():
            raise ValueError(
                f"HIP-3 midpoint {column} values must be finite and positive"
            )
    _validate_market_features(bars)


def _validate_market_features(bars: pd.DataFrame) -> None:
    """Reject malformed quotes or microstructure values at causal boundaries."""
    for prefix in ("entry", "decision"):
        bids = bars[f"{prefix}_bid"].astype(float)
        asks = bars[f"{prefix}_ask"].astype(float)
        valid = bids.map(isfinite) & asks.map(isfinite)
        if not valid.all() or bids.le(0.0).any() or asks.le(0.0).any():
            raise ValueError("HIP-3 executable quotes must be finite and positive")
        if bids.gt(asks).any():
            raise ValueError("HIP-3 executable quotes must not be crossed")
    micro = bars["decision_micro_price"].astype(float)
    spread = bars["decision_spread_bps"].astype(float)
    if not micro.map(isfinite).all() or micro.le(0.0).any():
        raise ValueError("HIP-3 decision microprice must be finite and positive")
    if not spread.map(isfinite).all() or spread.lt(0.0).any():
        raise ValueError("HIP-3 decision spread must be finite and non-negative")
    for column in ("decision_imbalance_5", "decision_imbalance_10"):
        values = bars[column].astype(float)
        if not values.map(isfinite).all() or values.abs().gt(1.0).any():
            raise ValueError("HIP-3 decision imbalance must be finite in [-1, 1]")


def _gap_before(index: pd.DatetimeIndex, bar_minutes: int) -> pd.Series:
    elapsed = index.to_series().diff().dt.total_seconds()
    gaps = (elapsed / (bar_minutes * 60) - 1).fillna(0.0).clip(lower=0.0)
    return gaps.round().astype(int).rename("gap_before_bars")


def _expected_bar_count(
    start_utc: pd.Timestamp, end_utc: pd.Timestamp, bar_minutes: int
) -> int:
    seconds = max((end_utc - start_utc).total_seconds(), 0.0)
    return int(seconds // (bar_minutes * 60))


def _utc(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")
