"""Read-only causal inputs for BTC subminute sell-flow absorption research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


_BUCKET_MS = 10_000
_MAXIMUM_ANCHOR_AGE_MS = 60_000
_QUERY_CHUNK = timedelta(days=7)
_RELATION_COLUMNS: dict[str, frozenset[str]] = {
    "archive_bundles": frozenset(
        {
            "bundle_id",
            "symbol",
            "start_utc",
            "end_utc",
            "depth",
            "book_rows",
            "trade_rows",
            "book_manifest_sha256",
            "trade_manifest_sha256",
            "fingerprint",
        }
    ),
    "book_snapshots": frozenset(
        {
            "symbol",
            "ts_exchange_ms",
            "bid_depth_10",
            "imbalance_10",
            "mid_price",
            "spread_bps",
        }
    ),
    "public_trades": frozenset(
        {
            "symbol",
            "trade_id",
            "ts_exchange_ms",
            "aggressor_side",
            "price",
            "size",
            "bundle_id",
        }
    ),
}
_FEATURE_SQL = """
WITH books AS (
    SELECT symbol, (ts_exchange_ms // 10000) * 10000 AS bucket_ms,
           count(*) AS snapshot_count,
           arg_min(mid_price, ts_exchange_ms) AS first_mid,
           arg_max(mid_price, ts_exchange_ms) AS last_mid,
           arg_min(bid_depth_10, ts_exchange_ms) AS first_bid_depth,
           min(bid_depth_10) AS minimum_bid_depth,
           arg_max(bid_depth_10, ts_exchange_ms) AS last_bid_depth,
           arg_max(imbalance_10, ts_exchange_ms) AS terminal_imbalance_10,
           max(spread_bps) AS maximum_spread_bps
    FROM book_snapshots
    WHERE symbol = 'BTC' AND ts_exchange_ms >= epoch_ms(?)
      AND ts_exchange_ms < epoch_ms(?)
    GROUP BY symbol, bucket_ms
), deduplicated_trades AS (
    SELECT trades.symbol, trades.trade_id, trades.ts_exchange_ms,
           trades.aggressor_side, trades.price, trades.size
    FROM public_trades AS trades
    INNER JOIN archive_bundles AS bundles USING (bundle_id)
    WHERE trades.symbol = 'BTC' AND trades.ts_exchange_ms >= epoch_ms(?)
      AND trades.ts_exchange_ms < epoch_ms(?)
    QUALIFY row_number() OVER (
        PARTITION BY trades.symbol, trades.trade_id
        ORDER BY bundles.start_utc DESC, trades.bundle_id,
                 trades.ts_exchange_ms, trades.trade_id
    ) = 1
), trades AS (
    SELECT symbol, (ts_exchange_ms // 10000) * 10000 AS bucket_ms,
           coalesce(sum(price * size) FILTER (
               WHERE lower(aggressor_side) = 'sell'), 0.0) AS sell_notional_usd,
           sum(price * size) AS total_notional_usd
    FROM deduplicated_trades
    GROUP BY symbol, bucket_ms
), features AS (
    SELECT books.*, trades.sell_notional_usd, trades.total_notional_usd,
           trades.sell_notional_usd / nullif(trades.total_notional_usd, 0.0)
               AS sell_share,
           greatest(0.0, (first_mid - last_mid) / first_mid * 10000.0)
               AS adverse_midpoint_bps,
           (first_bid_depth - minimum_bid_depth)
               / nullif(first_bid_depth, 0.0) AS bid_depletion_fraction,
           coalesce(
               (last_bid_depth - minimum_bid_depth)
                   / nullif(first_bid_depth - minimum_bid_depth, 0.0),
               0.0
           ) AS bid_recovery_fraction
    FROM books INNER JOIN trades USING (symbol, bucket_ms)
), prefiltered AS (
    SELECT * FROM features
    WHERE snapshot_count >= 5
      AND sell_notional_usd >= 5500000.0
      AND sell_share >= 0.75
), deduplicated_anchor_trades AS (
    SELECT trades.symbol, trades.trade_id, trades.ts_exchange_ms,
           trades.ts_utc, trades.price
    FROM public_trades AS trades
    INNER JOIN archive_bundles AS bundles USING (bundle_id)
    WHERE trades.symbol = 'BTC'
      AND trades.ts_exchange_ms >= epoch_ms(? - INTERVAL 61 MINUTE)
      AND trades.ts_exchange_ms < epoch_ms(? - INTERVAL 59 MINUTE)
    QUALIFY row_number() OVER (
        PARTITION BY trades.symbol, trades.trade_id
        ORDER BY bundles.start_utc DESC, trades.bundle_id,
                 trades.ts_exchange_ms, trades.trade_id
    ) = 1
), anchor_bars AS (
    SELECT symbol, time_bucket(INTERVAL '1 minute', ts_utc) AS bar_open_at,
           last(price ORDER BY ts_exchange_ms, trade_id) AS close
    FROM deduplicated_anchor_trades
    GROUP BY symbol, bar_open_at
), anchored AS (
    SELECT prefiltered.*, bars.bar_open_at AS anchor_at_utc,
           bars.close AS anchor_close,
           epoch_ms(to_timestamp(bucket_ms / 1000.0) - INTERVAL 60 MINUTE)
               AS requested_anchor_ms
    FROM prefiltered
    ASOF LEFT JOIN anchor_bars AS bars
      ON prefiltered.symbol = bars.symbol
     AND to_timestamp(bucket_ms / 1000.0) - INTERVAL 60 MINUTE
         >= bars.bar_open_at
)
SELECT *,
       to_timestamp(bucket_ms / 1000.0) AS bucket_start_utc,
       to_timestamp((bucket_ms + 10000) / 1000.0) AS available_at_utc,
       epoch_ms(anchor_at_utc) AS anchor_ms,
       (last_mid / anchor_close - 1.0) * 10000.0 AS prior_60m_trend_bps
FROM anchored
ORDER BY bucket_ms
"""
_SOURCE_SQL = """
SELECT bundle_id, start_utc, end_utc, depth, book_rows, trade_rows,
       book_manifest_sha256, trade_manifest_sha256, fingerprint
FROM archive_bundles
WHERE symbol = 'BTC' AND start_utc >= ? AND end_utc <= ?
ORDER BY start_utc, end_utc, bundle_id
"""


@dataclass(frozen=True)
class BtcAbsorptionWindow:
    """One half-open UTC archive extraction window."""

    start_utc: datetime
    end_utc: datetime

    def __post_init__(self) -> None:
        if self.start_utc.tzinfo is None or self.end_utc.tzinfo is None:
            raise ValueError("BTC absorption bounds must be timezone-aware")
        if self.start_utc >= self.end_utc:
            raise ValueError("BTC absorption start must precede end")


@dataclass(frozen=True)
class BtcAbsorptionSourceEvidence:
    """Stable archive-bundle identity for one requested window."""

    bundle_identity_sha256: str
    bundles: int
    book_rows_manifest: int
    trade_rows_manifest: int
    empty_book_bundles: int
    empty_trade_bundles: int


@dataclass(frozen=True)
class BtcAbsorptionInputs:
    """Causal ten-second features plus source and rejection evidence."""

    features: pd.DataFrame
    source: BtcAbsorptionSourceEvidence
    rejections: dict[str, int]


def load_btc_absorption_inputs(
    database_path: Path,
    window: BtcAbsorptionWindow,
) -> BtcAbsorptionInputs:
    """Load causal ten-second BTC features from a read-only research database."""
    if not database_path.is_file():
        raise FileNotFoundError(f"research database does not exist: {database_path}")
    with duckdb.connect(str(database_path), read_only=True) as connection:
        _configure(connection)
        _validate_schema(connection)
        source = _source_evidence(connection, window)
        raw = _query_features(connection, window)
    return _validated_inputs(raw, source)


def btc_absorption_source_evidence(
    database_path: Path,
    window: BtcAbsorptionWindow,
) -> BtcAbsorptionSourceEvidence:
    """Return registered archive identity without scanning market events."""
    if not database_path.is_file():
        raise FileNotFoundError(f"research database does not exist: {database_path}")
    with duckdb.connect(str(database_path), read_only=True) as connection:
        _configure(connection)
        _validate_schema(connection)
        return _source_evidence(connection, window)


def _configure(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("SET TimeZone='UTC'")
    connection.execute("SET enable_progress_bar=false")
    connection.execute("SET threads=2")
    connection.execute("SET preserve_insertion_order=false")


def _query_features(
    connection: duckdb.DuckDBPyConnection,
    window: BtcAbsorptionWindow,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    start = window.start_utc
    while start < window.end_utc:
        end = min(start + _QUERY_CHUNK, window.end_utc)
        frames.append(connection.execute(_FEATURE_SQL, [start, end] * 3).df())
        start = end
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _validate_schema(connection: duckdb.DuckDBPyConnection) -> None:
    relations = {str(row[0]) for row in connection.execute("SHOW TABLES").fetchall()}
    missing = sorted(set(_RELATION_COLUMNS).difference(relations))
    if missing:
        raise ValueError(f"BTC absorption database missing relations: {missing}")
    for relation, expected in _RELATION_COLUMNS.items():
        columns = {
            str(row[0]) for row in connection.execute(f"DESCRIBE {relation}").fetchall()
        }
        absent = sorted(expected.difference(columns))
        if absent:
            raise ValueError(f"{relation} missing BTC absorption columns: {absent}")


def _source_evidence(
    connection: duckdb.DuckDBPyConnection,
    window: BtcAbsorptionWindow,
) -> BtcAbsorptionSourceEvidence:
    rows = connection.execute(
        _SOURCE_SQL,
        [window.start_utc, window.end_utc],
    ).fetchall()
    if not rows:
        raise ValueError("BTC absorption window has no registered archive bundles")
    digest = hashlib.sha256()
    for row in rows:
        digest.update(("|".join(str(value) for value in row) + "\n").encode())
    return BtcAbsorptionSourceEvidence(
        digest.hexdigest(),
        len(rows),
        sum(int(row[4]) for row in rows),
        sum(int(row[5]) for row in rows),
        sum(int(row[4]) == 0 for row in rows),
        sum(int(row[5]) == 0 for row in rows),
    )


def _validated_inputs(
    raw: pd.DataFrame,
    source: BtcAbsorptionSourceEvidence,
) -> BtcAbsorptionInputs:
    if raw.empty:
        return BtcAbsorptionInputs(raw, source, {})
    _normalize_times(raw)
    _validate_numeric(raw)
    anchor_age = raw["requested_anchor_ms"] - raw["anchor_ms"]
    valid = raw["anchor_ms"].notna() & anchor_age.between(
        0, _MAXIMUM_ANCHOR_AGE_MS, inclusive="both"
    )
    features = raw.loc[valid].reset_index(drop=True)
    rejected = int((~valid).sum())
    reasons = {"prior_60m_anchor_stale_or_missing": rejected} if rejected else {}
    return BtcAbsorptionInputs(features, source, reasons)


def _normalize_times(frame: pd.DataFrame) -> None:
    for column in ("bucket_start_utc", "available_at_utc", "anchor_at_utc"):
        frame[column] = pd.to_datetime(frame[column], utc=True)


def _validate_numeric(frame: pd.DataFrame) -> None:
    columns = (
        "first_mid",
        "last_mid",
        "first_bid_depth",
        "minimum_bid_depth",
        "last_bid_depth",
        "sell_notional_usd",
        "total_notional_usd",
    )
    values = frame.loc[:, columns].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0.0).any():
        raise ValueError("BTC absorption inputs contain nonpositive market values")
    if frame["bucket_ms"].duplicated().any():
        raise RuntimeError("BTC absorption input buckets are duplicated")
    if not frame["bucket_ms"].is_monotonic_increasing:
        raise RuntimeError("BTC absorption input buckets are unordered")
