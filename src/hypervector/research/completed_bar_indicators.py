"""Shared causal OHLC resampling and Wilder indicator primitives."""

from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.typing import NDArray

OHLC_COLUMNS = ("open", "high", "low", "close")


def validated_ohlc_bars(bars: pd.DataFrame, *, label: str) -> pd.DataFrame:
    """Return chronological finite OHLC values after strict validation."""
    missing = set(OHLC_COLUMNS).difference(bars.columns)
    if missing:
        raise ValueError(f"{label} bars missing columns: {sorted(missing)}")
    if len(bars) < 2 or not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError(f"{label} requires at least two datetime-indexed bars")
    if not bars.index.is_unique or not bars.index.is_monotonic_increasing:
        raise ValueError(f"{label} bars require a unique increasing index")
    if bars.index.tz is None:
        raise ValueError(f"{label} bar timestamps must be timezone-aware")
    frame = bars.loc[:, list(OHLC_COLUMNS)].astype(np.float64).copy()
    values = frame.to_numpy(dtype=np.float64)
    if not np.isfinite(values).all() or (values <= 0.0).any():
        raise ValueError(f"{label} OHLC values must be finite and positive")
    if (frame["high"] < frame.max(axis=1)).any():
        raise ValueError(f"{label} high values are inconsistent")
    if (frame["low"] > frame.min(axis=1)).any():
        raise ValueError(f"{label} low values are inconsistent")
    return frame


def contiguous_segment_ids(
    index: pd.DatetimeIndex,
    expected: pd.Timedelta,
) -> NDArray[np.int64]:
    """Identify contiguous bar segments without bridging unknown intervals."""
    segments = np.zeros(len(index), dtype=np.int64)
    if len(index) > 1:
        breaks = index.to_series().diff().iloc[1:].ne(expected).to_numpy()
        segments[1:] = np.cumsum(breaks, dtype=np.int64)
    return segments


def raw_true_range(
    frame: pd.DataFrame,
    segments: NDArray[np.int64],
) -> NDArray[np.float64]:
    """Return real-OHLC true range, resetting previous-close use at gaps."""
    high = frame["high"].to_numpy(dtype=np.float64)
    low = frame["low"].to_numpy(dtype=np.float64)
    close = frame["close"].to_numpy(dtype=np.float64)
    result = high - low
    for position in range(1, len(frame)):
        if segments[position] == segments[position - 1]:
            result[position] = max(
                result[position],
                abs(high[position] - close[position - 1]),
                abs(low[position] - close[position - 1]),
            )
    return result


def segmented_wilder_rma(
    values: NDArray[np.float64],
    segments: NDArray[np.int64],
    period: int,
) -> NDArray[np.float64]:
    """Return SMA-seeded Wilder RMA independently within each segment."""
    if isinstance(period, bool) or period < 1:
        raise ValueError("Wilder period must be a positive integer")
    result = np.full(len(values), np.nan, dtype=np.float64)
    for segment in np.unique(segments):
        positions = np.flatnonzero(segments == segment)
        if len(positions) < period:
            continue
        seed_position = int(positions[period - 1])
        result[seed_position] = float(values[positions[:period]].mean())
        for position in positions[period:]:
            prior = result[position - 1]
            result[position] = (prior * (period - 1) + values[position]) / period
    return result


def complete_resampled_ohlc(
    frame: pd.DataFrame,
    *,
    source_minutes: int,
    target_hours: int,
) -> pd.DataFrame:
    """Aggregate only complete, boundary-aligned higher-timeframe OHLC bars."""
    interval = pd.Timedelta(minutes=source_minutes)
    if not frame.index.floor(f"{source_minutes}min").equals(frame.index):
        raise ValueError("source bars are not aligned to their UTC boundaries")
    expected = target_hours * 60 // source_minutes
    grouped = frame.resample(
        f"{target_hours}h", origin="epoch", label="left", closed="left"
    )
    aggregate = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        count=("close", "count"),
    )
    boundaries = (
        frame.index.to_series()
        .resample(f"{target_hours}h", origin="epoch", label="left", closed="left")
        .agg(["min", "max"])
    )
    complete = (
        aggregate["count"].eq(expected)
        & boundaries["min"].eq(aggregate.index)
        & boundaries["max"].eq(aggregate.index + interval * (expected - 1))
    )
    return aggregate.loc[complete, list(OHLC_COLUMNS)]
