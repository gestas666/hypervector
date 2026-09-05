"""Shared causal completed-bar validation for BTC research experiments."""

from __future__ import annotations

import numpy as np
import pandas as pd


_REQUIRED_COLUMNS = frozenset({"open", "high", "low", "close", "volume"})
_MINUTE = pd.Timedelta(minutes=1)


def validated_btc_minute_bars(bars: pd.DataFrame, label: str) -> pd.DataFrame:
    """Return validated minute evidence with explicit causal gap segments."""
    missing = sorted(_REQUIRED_COLUMNS.difference(bars.columns))
    if missing:
        raise ValueError(f"{label} bars missing columns: {missing}")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError(f"{label} bars require an aware DatetimeIndex")
    if not bars.index.is_unique or not bars.index.is_monotonic_increasing:
        raise ValueError(f"{label} bars must be unique and increasing")
    cadence = bars.index.to_series().diff().dropna()
    if len(bars) < 2 or not cadence.eq(_MINUTE).all():
        raise ValueError(f"{label} requires uninterrupted minute cadence")
    columns = sorted(_REQUIRED_COLUMNS)
    if "gap_before_bars" in bars:
        columns.append("gap_before_bars")
    selected = bars.loc[:, columns].astype(float).copy()
    _validate_market_values(selected, label)
    gaps = selected.get("gap_before_bars", pd.Series(0.0, index=selected.index))
    if (gaps < 0.0).any() or not gaps.mod(1.0).eq(0.0).all():
        raise ValueError(f"{label} gap counts must be nonnegative integers")
    selected["_gap_marker"] = gaps.gt(0.0)
    selected["segment_id"] = selected["_gap_marker"].cumsum().astype(int)
    return selected


def completed_btc_bars(
    bars: pd.DataFrame,
    rule: str,
    expected_minutes: int,
) -> pd.DataFrame:
    """Aggregate only complete bars that do not cross explicit gap segments."""
    grouped = bars.resample(rule, label="left", closed="left")
    aggregated = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        segment_id=("segment_id", "first"),
        segment_last=("segment_id", "last"),
        gap_marker=("_gap_marker", "max"),
    )
    complete = (
        grouped.size().eq(expected_minutes)
        & aggregated["segment_id"].eq(aggregated["segment_last"])
        & ~aggregated["gap_marker"]
    )
    return (
        aggregated.loc[complete].drop(columns=["segment_last", "gap_marker"]).dropna()
    )


def _validate_market_values(bars: pd.DataFrame, label: str) -> None:
    ohlc = bars.loc[:, ["open", "high", "low", "close"]]
    if not np.isfinite(ohlc.to_numpy()).all() or (ohlc <= 0.0).any().any():
        raise ValueError(f"{label} OHLC must be finite and positive")
    volume = bars["volume"].to_numpy(dtype=float)
    if not np.isfinite(volume).all() or (volume < 0.0).any():
        raise ValueError(f"{label} volume must be finite and non-negative")
    if (ohlc["high"] < ohlc.max(axis=1)).any():
        raise ValueError(f"{label} high is internally inconsistent")
    if (ohlc["low"] > ohlc.min(axis=1)).any():
        raise ValueError(f"{label} low is internally inconsistent")
