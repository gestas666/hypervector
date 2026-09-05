"""Causal UT/ATR flip signals for the V69 research candidate."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from hypervector.research.completed_bar_indicators import (
    OHLC_COLUMNS,
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
class UtAtrFlipConfig:
    """Immutable parameters for one independently implemented signal contract."""

    atr_period: int = 13
    key_value: float = 1.0
    signal_hours: int = 4
    execution_minutes: int = 15

    def __post_init__(self) -> None:
        """Reject values outside the preregistered V69 architecture."""
        if isinstance(self.atr_period, bool) or self.atr_period < 1:
            raise ValueError("atr_period must be a positive integer")
        if not math.isfinite(self.key_value) or self.key_value <= 0.0:
            raise ValueError("key_value must be positive and finite")
        if self.signal_hours != 4:
            raise ValueError("V69 signal_hours must equal 4")
        if self.execution_minutes != 15:
            raise ValueError("V69 execution_minutes must equal 15")


def build_ut_atr_flip_state(
    signal_bars: pd.DataFrame,
    config: UtAtrFlipConfig | None = None,
) -> pd.DataFrame:
    """Return append-invariant state and flips for completed signal bars."""
    cfg = config or UtAtrFlipConfig()
    frame = validated_ohlc_bars(signal_bars, label="UT/ATR")
    segments = contiguous_segment_ids(
        frame.index,
        pd.Timedelta(hours=cfg.signal_hours),
    )
    source = frame.loc[:, list(OHLC_COLUMNS)].mean(axis=1).to_numpy(np.float64)
    true_range = raw_true_range(frame, segments)
    atr = segmented_wilder_rma(true_range, segments, cfg.atr_period)
    stop, long_entry, short_entry = _ut_recurrence(
        source,
        atr,
        segments,
        cfg.key_value,
    )
    return pd.DataFrame(
        {
            "signal_source": source,
            "true_range": true_range,
            "atr": atr,
            "trailing_stop": stop,
            "long_entry": long_entry,
            "short_entry": short_entry,
        },
        index=frame.index,
    )


def build_ut_atr_flip_signals(
    execution_bars: pd.DataFrame,
    config: UtAtrFlipConfig | None = None,
) -> pd.DataFrame:
    """Map completed 4h flips onto the last known 15m bar for next-open fills."""
    cfg = config or UtAtrFlipConfig()
    frame = validated_ohlc_bars(execution_bars, label="UT/ATR")
    signal_bars = complete_resampled_ohlc(
        frame,
        source_minutes=cfg.execution_minutes,
        target_hours=cfg.signal_hours,
    )
    state = build_ut_atr_flip_state(signal_bars, cfg)
    output = empty_directional_signals(
        frame.index,
        signal_name="ut_atr_flip_variant_r_v1",
        source_time_column="ut_signal_bar_open",
    )
    project_completed_entries(
        output,
        state,
        signal_hours=cfg.signal_hours,
        execution_minutes=cfg.execution_minutes,
        state_stop_column="trailing_stop",
        source_time_column="ut_signal_bar_open",
        label="UT/ATR signal",
    )
    return output


def _ut_recurrence(
    source: NDArray[np.float64],
    atr: NDArray[np.float64],
    segments: NDArray[np.int64],
    key_value: float,
) -> tuple[NDArray[np.float64], NDArray[np.bool_], NDArray[np.bool_]]:
    stop = np.full(len(source), np.nan, dtype=np.float64)
    long_entry = np.zeros(len(source), dtype=np.bool_)
    short_entry = np.zeros(len(source), dtype=np.bool_)
    for position in range(len(source)):
        if not math.isfinite(float(atr[position])):
            continue
        prior_position = position - 1
        same_segment = prior_position >= 0 and (
            segments[position] == segments[prior_position]
        )
        prior_source = source[prior_position] if same_segment else math.nan
        prior_stop = stop[prior_position] if same_segment else math.nan
        stop[position] = _next_stop(
            source[position], prior_source, prior_stop, key_value * atr[position]
        )
        if math.isfinite(prior_stop):
            long_entry[position] = (
                source[position] > stop[position] and prior_source <= prior_stop
            )
            short_entry[position] = (
                stop[position] > source[position] and prior_stop <= prior_source
            )
    return stop, long_entry, short_entry


def _next_stop(
    source: float,
    prior_source: float,
    prior_stop: float,
    loss_distance: float,
) -> float:
    previous = prior_stop if math.isfinite(prior_stop) else 0.0
    if math.isfinite(prior_source) and source > previous and prior_source > previous:
        return max(previous, source - loss_distance)
    if math.isfinite(prior_source) and source < previous and prior_source < previous:
        return min(previous, source + loss_distance)
    return source - loss_distance if source > previous else source + loss_distance
