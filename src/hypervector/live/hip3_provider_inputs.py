"""Validated completed 15-minute inputs for HIP-3 live providers."""

from __future__ import annotations

import pandas as pd

BAR_INTERVAL = pd.Timedelta(minutes=15)


def completed_hip3_inputs(
    bars: pd.DataFrame,
    observed_at: pd.Timestamp,
    after_decision_time_ms: int | None,
) -> tuple[pd.DataFrame, tuple[pd.Timestamp, ...], int]:
    """Return the causal frame, unseen decision rows, and advanced boundary."""
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise ValueError(f"HIP-3 provider bars missing columns: {missing}")
    observed = pd.Timestamp(observed_at)
    if observed.tzinfo is None:
        raise ValueError("HIP-3 observed_at must be timezone-aware")
    frame = bars.loc[:, sorted(required)].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    index = pd.DatetimeIndex(frame.pop("timestamp"))
    if index.empty or not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError("HIP-3 provider bars must be ordered and unique")
    frame.index = index
    frame = frame.loc[index + BAR_INTERVAL <= observed.tz_convert("UTC")].copy()
    if frame.empty:
        raise ValueError("HIP-3 provider has no completed 15m bar")
    frame["gap_before_bars"] = _gap_counts(frame.index)
    prior = _boundary(after_decision_time_ms)
    positions = tuple(
        timestamp for timestamp in frame.index if decision_time_ms(timestamp) > prior
    )
    boundary = decision_time_ms(frame.index[-1]) if positions else prior
    return frame, positions, boundary


def decision_time_ms(timestamp: pd.Timestamp) -> int:
    """Return the close-known decision timestamp for one 15-minute bar."""
    return int((timestamp + BAR_INTERVAL).timestamp() * 1_000)


def _gap_counts(index: pd.DatetimeIndex) -> pd.Series:
    intervals = index.to_series().diff() / BAR_INTERVAL
    return intervals.sub(1).clip(lower=0).fillna(0).astype(int)


def _boundary(value: int | None) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("HIP-3 decision boundary must be nonnegative")
    return value
