"""Causal completed-bar aggregation for Cipher suite research."""

from __future__ import annotations

import numpy as np
import pandas as pd


_BUNDLE_COLUMNS = (
    "cipher_a_trend",
    "cipher_b_trigger",
    "cipher_b_cross_trigger",
    "cipher_b_money_flow",
    "cipher_dbsi",
)


def resample_cipher_bars(bars: pd.DataFrame, *, bar_minutes: int) -> pd.DataFrame:
    """Return five-minute bars or complete supported higher-timeframe buckets."""
    _validate_bars(bars)
    columns = ["bar_open_at", "open", "high", "low", "close", "volume"]
    if bar_minutes == 5:
        return bars.loc[:, columns].copy().reset_index(drop=True)
    if bar_minutes not in {15, 30, 60}:
        raise ValueError("Cipher bar duration must be 5, 15, 30, or 60 minutes")
    indexed = bars.loc[:, columns].set_index("bar_open_at")
    grouped = indexed.resample(f"{bar_minutes}min", label="left", closed="left")
    output = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        constituent_bars=("close", "count"),
    )
    complete = output["constituent_bars"].eq(bar_minutes // 5)
    return output.loc[complete].drop(columns="constituent_bars").reset_index()


def align_cipher_bundle_timeframes(
    execution: pd.DataFrame,
    trend: pd.DataFrame,
    *,
    trend_minutes: int,
) -> pd.DataFrame:
    """Align closed A-trend bars to lower-timeframe B/DBSI components causally."""
    _validate_components(execution, "execution")
    _validate_components(trend, "trend")
    if trend_minutes < 1:
        raise ValueError("Cipher trend duration must be positive")
    duration = pd.Timedelta(minutes=trend_minutes)
    left = pd.DataFrame({"execution_time": execution.index})
    right = pd.DataFrame(
        {
            "available_at": trend.index + duration,
            "cipher_a_trend": trend["cipher_a_trend"].to_numpy(),
        }
    )
    merged = pd.merge_asof(
        left, right, left_on="execution_time", right_on="available_at"
    )
    age = merged["execution_time"] - merged["available_at"]
    fresh = merged["available_at"].notna() & age.lt(duration)
    output = execution.loc[:, list(_BUNDLE_COLUMNS)].copy()
    output["cipher_a_trend"] = np.where(
        fresh, merged["cipher_a_trend"].fillna(0), 0
    ).astype(np.int8)
    return output


def _validate_bars(bars: pd.DataFrame) -> None:
    required = {"bar_open_at", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise ValueError(f"Cipher timeframe bars missing columns: {missing}")
    times = pd.DatetimeIndex(bars["bar_open_at"])
    if bars.empty or times.tz is None:
        raise ValueError("Cipher timeframe bars must be non-empty and timezone-aware")
    if not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("Cipher timeframe bars must be ordered and unique")
    values = bars[["open", "high", "low", "close", "volume"]].to_numpy(float)
    if not np.isfinite(values).all() or (values[:, :4] <= 0.0).any():
        raise ValueError("Cipher timeframe OHLCV must be finite with positive prices")
    if (values[:, 4] < 0.0).any():
        raise ValueError("Cipher timeframe volume must be non-negative")


def _validate_components(frame: pd.DataFrame, label: str) -> None:
    if tuple(frame.columns) != _BUNDLE_COLUMNS:
        raise ValueError(f"Cipher {label} components have unexpected columns")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError(f"Cipher {label} components require an aware index")
    if frame.empty or not frame.index.is_monotonic_increasing:
        raise ValueError(f"Cipher {label} components must be non-empty and ordered")
    if frame.index.has_duplicates:
        raise ValueError(f"Cipher {label} component timestamps must be unique")
    if not np.isin(frame.to_numpy(dtype=np.int8), (-1, 0, 1)).all():
        raise ValueError(f"Cipher {label} component values must be -1, 0, or +1")
