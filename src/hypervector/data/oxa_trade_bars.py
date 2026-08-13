"""Minute-bar aggregation for normalized 0xArchive public trades."""

from __future__ import annotations

import pandas as pd


def trade_rows_to_minute_bars(trades: pd.DataFrame) -> pd.DataFrame:
    """Aggregate a globally ordered public tape into complete minute bars."""
    minute = pd.to_datetime(trades["ts_ms"], unit="ms", utc=True).dt.floor("min")
    ordered = trades.assign(minute=minute).sort_values(["ts_ms", "trade_id"])
    bars = ordered.groupby("minute").agg(
        trade_open=("price", "first"),
        trade_high=("price", "max"),
        trade_low=("price", "min"),
        trade_close=("price", "last"),
        trade_volume=("size", "sum"),
        trade_trade_count=("trade_id", "count"),
    )
    bars.index = pd.DatetimeIndex(bars.index)
    return bars


def empty_trade_bars() -> pd.DataFrame:
    """Return a typed empty frame matching normalized minute-bar columns."""
    columns = [
        "trade_open",
        "trade_high",
        "trade_low",
        "trade_close",
        "trade_volume",
        "trade_trade_count",
    ]
    return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], tz="UTC"))
