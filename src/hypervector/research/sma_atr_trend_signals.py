"""Causal completed-4h SMA trend signals with ATR structural stops."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from hypervector.research.completed_bar_indicators import (
    complete_resampled_ohlc,
    contiguous_segment_ids,
    raw_true_range,
    segmented_wilder_rma,
    validated_ohlc_bars,
)
from hypervector.research.completed_signal_projection import (
    empty_directional_signals,
    project_completed_entries,
)


@dataclass(frozen=True)
class SmaAtrTrendConfig:
    """Immutable parameters for one slow trend and volatility-stop contract."""

    fast_period: int = 10
    slow_period: int = 30
    atr_period: int = 14
    atr_multiple: float = 2.0
    signal_hours: int = 4
    execution_minutes: int = 15

    def __post_init__(self) -> None:
        """Reject values outside a coherent causal trend specification."""
        periods = (self.fast_period, self.slow_period, self.atr_period)
        if any(isinstance(value, bool) or value < 1 for value in periods):
            raise ValueError("SMA/ATR periods must be positive integers")
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be below slow_period")
        if not math.isfinite(self.atr_multiple) or self.atr_multiple <= 0.0:
            raise ValueError("atr_multiple must be positive and finite")
        if self.signal_hours != 4 or self.execution_minutes != 15:
            raise ValueError("V73 requires completed 4h signals and 15m execution")


def build_sma_atr_trend_state(
    signal_bars: pd.DataFrame,
    config: SmaAtrTrendConfig | None = None,
) -> pd.DataFrame:
    """Return append-invariant SMA state, fresh crosses, and structural stops."""
    cfg = config or SmaAtrTrendConfig()
    frame = validated_ohlc_bars(signal_bars, label="SMA/ATR trend")
    segments = contiguous_segment_ids(
        frame.index,
        pd.Timedelta(hours=cfg.signal_hours),
    )
    close = frame["close"].to_numpy(dtype=np.float64)
    fast = _segmented_sma(close, segments, cfg.fast_period)
    slow = _segmented_sma(close, segments, cfg.slow_period)
    true_range = raw_true_range(frame, segments)
    atr = segmented_wilder_rma(true_range, segments, cfg.atr_period)
    long_entry, short_entry = _fresh_crosses(fast, slow, segments)
    stop = _entry_stops(close, atr, long_entry, short_entry, cfg.atr_multiple)
    return pd.DataFrame(
        {
            "fast_sma": fast,
            "slow_sma": slow,
            "atr": atr,
            "long_entry": long_entry,
            "short_entry": short_entry,
            "stop_price": stop,
        },
        index=frame.index,
    )


def build_sma_atr_trend_signals(
    execution_bars: pd.DataFrame,
    config: SmaAtrTrendConfig | None = None,
) -> pd.DataFrame:
    """Project completed 4h trend crosses for exactly next-15m-open execution."""
    cfg = config or SmaAtrTrendConfig()
    frame = validated_ohlc_bars(execution_bars, label="SMA/ATR trend")
    signal_bars = complete_resampled_ohlc(
        frame,
        source_minutes=cfg.execution_minutes,
        target_hours=cfg.signal_hours,
    )
    state = build_sma_atr_trend_state(signal_bars, cfg)
    output = empty_directional_signals(
        frame.index,
        signal_name="completed_4h_sma_10_30_atr_stop_v1",
        source_time_column="sma_atr_signal_bar_open",
    )
    project_completed_entries(
        output,
        state,
        signal_hours=cfg.signal_hours,
        execution_minutes=cfg.execution_minutes,
        state_stop_column="stop_price",
        source_time_column="sma_atr_signal_bar_open",
        label="SMA/ATR trend signal",
    )
    return output


def _segmented_sma(
    values: NDArray[np.float64],
    segments: NDArray[np.int64],
    period: int,
) -> NDArray[np.float64]:
    result = np.full(len(values), np.nan, dtype=np.float64)
    for segment in np.unique(segments):
        positions = np.flatnonzero(segments == segment)
        rolling = (
            pd.Series(values[positions]).rolling(period, min_periods=period).mean()
        )
        result[positions] = rolling.to_numpy(dtype=np.float64)
    return result


def _fresh_crosses(
    fast: NDArray[np.float64],
    slow: NDArray[np.float64],
    segments: NDArray[np.int64],
) -> tuple[NDArray[np.bool_], NDArray[np.bool_]]:
    long_entry = np.zeros(len(fast), dtype=np.bool_)
    short_entry = np.zeros(len(fast), dtype=np.bool_)
    for position in range(1, len(fast)):
        if segments[position] != segments[position - 1]:
            continue
        values = (
            fast[position],
            slow[position],
            fast[position - 1],
            slow[position - 1],
        )
        if not all(math.isfinite(float(value)) for value in values):
            continue
        long_entry[position] = (
            fast[position] > slow[position] and fast[position - 1] <= slow[position - 1]
        )
        short_entry[position] = (
            fast[position] < slow[position] and fast[position - 1] >= slow[position - 1]
        )
    return long_entry, short_entry


def _entry_stops(
    close: NDArray[np.float64],
    atr: NDArray[np.float64],
    long_entry: NDArray[np.bool_],
    short_entry: NDArray[np.bool_],
    multiplier: float,
) -> NDArray[np.float64]:
    stop = np.full(len(close), np.nan, dtype=np.float64)
    stop[long_entry] = close[long_entry] - multiplier * atr[long_entry]
    stop[short_entry] = close[short_entry] + multiplier * atr[short_entry]
    return stop
