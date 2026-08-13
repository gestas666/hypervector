"""Shared native-bar validation for the causal four-Pine stack."""

from __future__ import annotations

import numpy as np
import pandas as pd

_COLUMNS = ("bar_open_at", "open", "high", "low", "close", "volume")


def validated_native_bars(
    bars: pd.DataFrame,
    *,
    bar_minutes: int,
) -> pd.DataFrame:
    """Return ordered exact native bars or reject incomplete timing and prices."""
    if isinstance(bar_minutes, bool) or bar_minutes not in {15, 30}:
        raise ValueError("Pine stack bar duration must be 15 or 30 minutes")
    missing = sorted(set(_COLUMNS).difference(bars.columns))
    if missing:
        raise ValueError(f"Pine stack bars missing columns: {missing}")
    frame = bars.loc[:, list(_COLUMNS)].copy().reset_index(drop=True)
    times = pd.DatetimeIndex(frame["bar_open_at"])
    if frame.empty or times.tz is None:
        raise ValueError("Pine stack bars must be non-empty and timezone-aware")
    if not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("Pine stack bars must be ordered and unique")
    aligned = times == times.floor(f"{bar_minutes}min")
    spacing = times.to_series(index=range(len(times))).diff().iloc[1:]
    expected = pd.Timedelta(minutes=bar_minutes)
    if not aligned.all() or (not spacing.empty and not spacing.eq(expected).all()):
        raise ValueError(f"Pine stack requires exact native {bar_minutes}-minute bars")
    values = frame[["open", "high", "low", "close", "volume"]].to_numpy(float)
    if not np.isfinite(values).all() or (values[:, :4] <= 0.0).any():
        raise ValueError("Pine stack OHLCV must be finite with positive prices")
    if (values[:, 4] < 0.0).any():
        raise ValueError("Pine stack volume must be non-negative")
    if (values[:, 1] < values[:, [0, 3]].max(axis=1)).any():
        raise ValueError("Pine stack high cannot be below open or close")
    if (values[:, 2] > values[:, [0, 3]].min(axis=1)).any():
        raise ValueError("Pine stack low cannot be above open or close")
    return frame
