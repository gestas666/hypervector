"""Receipt-causal minute inputs for OI deleveraging research."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd


_MINUTE_NS = 60_000_000_000
_EXPECTED_SOURCES = {
    "live_asset_contexts": "hyperliquid_ws_activeAssetCtx",
    "replay_live_book_snapshots": "hyperliquid_ws_l2Book",
    "replay_live_public_trades": "hyperliquid_ws_trades",
}


def load_oi_deleveraging_minutes(
    database: Path,
    symbol: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Load common OI, trade, and L2 minutes using receipt-time causality."""
    if not database.is_file():
        raise ValueError(f"OI deleveraging database does not exist: {database}")
    if not symbol or start >= end:
        raise ValueError("OI deleveraging symbol/window is invalid")
    lower, upper = _nanoseconds(start), _nanoseconds(end)
    with duckdb.connect(str(database), read_only=True) as connection:
        _require_sources(connection, symbol, lower, upper)
        rows = connection.execute(
            _MINUTE_QUERY,
            [symbol, lower, upper, symbol, lower, upper, symbol, lower, upper],
        ).fetch_df()
    if rows.empty:
        return _empty_minutes()
    rows["minute"] = pd.to_datetime(rows["minute_bucket"] * 60, unit="s", utc=True)
    rows["first_quote_at"] = pd.to_datetime(
        rows.pop("first_quote_ns"), unit="ns", utc=True
    )
    return rows.drop(columns="minute_bucket").loc[:, _OUTPUT_COLUMNS]


def _require_sources(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
    lower: int,
    upper: int,
) -> None:
    for table, expected in _EXPECTED_SOURCES.items():
        values = connection.execute(
            f"SELECT DISTINCT source FROM {table} "
            "WHERE symbol = ? AND received_ts_ns >= ? AND received_ts_ns < ?",
            [symbol, lower, upper],
        ).fetchall()
        observed = {str(row[0]) for row in values}
        if observed != {expected}:
            raise ValueError(
                f"OI deleveraging {table} source mismatch: {sorted(observed)}"
            )


def _nanoseconds(value: datetime) -> int:
    if value.tzinfo is None:
        raise ValueError("OI deleveraging timestamps must be timezone-aware")
    return int(value.timestamp() * 1_000_000_000)


def _empty_minutes() -> pd.DataFrame:
    return pd.DataFrame(columns=_OUTPUT_COLUMNS)


_OUTPUT_COLUMNS = [
    "minute",
    "close",
    "trade_imbalance",
    "book_imbalance",
    "open_interest",
    "first_bid",
    "first_ask",
    "first_quote_at",
]


_MINUTE_QUERY = f"""
WITH trades AS (
    SELECT received_ts_ns // {_MINUTE_NS} AS minute_bucket,
           arg_max(price, struct_pack(ts := received_ts_ns, id := trade_id)) AS close,
           sum(CASE WHEN aggressor_side = 'buy' THEN price * size ELSE 0 END)
             AS buy_notional,
           sum(CASE WHEN aggressor_side = 'sell' THEN price * size ELSE 0 END)
             AS sell_notional
    FROM replay_live_public_trades
    WHERE symbol = ? AND received_ts_ns >= ? AND received_ts_ns < ?
    GROUP BY minute_bucket
), contexts AS (
    SELECT received_ts_ns // {_MINUTE_NS} AS minute_bucket,
           arg_max(open_interest, received_ts_ns) AS open_interest
    FROM live_asset_contexts
    WHERE symbol = ? AND received_ts_ns >= ? AND received_ts_ns < ?
    GROUP BY minute_bucket
), book_values AS (
    SELECT received_ts_ns,
           bids[1].px AS best_bid,
           asks[1].px AS best_ask,
           (SELECT sum(level.sz) FROM unnest(bids[:10]) AS item(level))
             AS bid_depth,
           (SELECT sum(level.sz) FROM unnest(asks[:10]) AS item(level))
             AS ask_depth
    FROM replay_live_book_snapshots
    WHERE symbol = ? AND received_ts_ns >= ? AND received_ts_ns < ?
), books AS (
    SELECT received_ts_ns // {_MINUTE_NS} AS minute_bucket,
           arg_min(best_bid, received_ts_ns) AS first_bid,
           arg_min(best_ask, received_ts_ns) AS first_ask,
           min(received_ts_ns) AS first_quote_ns,
           arg_max(
             (bid_depth - ask_depth) / nullif(bid_depth + ask_depth, 0),
             received_ts_ns
           ) AS book_imbalance
    FROM book_values
    GROUP BY minute_bucket
)
SELECT trades.minute_bucket,
       trades.close,
       (buy_notional - sell_notional) / nullif(buy_notional + sell_notional, 0)
         AS trade_imbalance,
       books.book_imbalance,
       contexts.open_interest,
       books.first_bid,
       books.first_ask,
       books.first_quote_ns
FROM trades
JOIN contexts USING (minute_bucket)
JOIN books USING (minute_bucket)
ORDER BY trades.minute_bucket
"""
