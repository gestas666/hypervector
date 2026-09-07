"""Completed-hour price-band recovery signals for report-only strategy research."""

from __future__ import annotations

import numpy as np
import pandas as pd

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

STRATEGY = "hourly_band20_reentry_atr20_bidirectional_v1"
PERIOD = 20
BAND_DEVIATIONS = 2.0
ATR_MULTIPLE = 2.0
SIGNAL_HOURS = 1
EXECUTION_MINUTES = 15


def build_hourly_band_reentry_signals(execution_bars: pd.DataFrame) -> pd.DataFrame:
    """Project closed-hour band recoveries and mean exits to the last 15m row."""
    frame = validated_ohlc_bars(execution_bars, label="hourly band re-entry")
    hourly = complete_resampled_ohlc(
        frame,
        source_minutes=EXECUTION_MINUTES,
        target_hours=SIGNAL_HOURS,
    )
    state = _hourly_state(hourly)
    output = empty_directional_signals(
        frame.index,
        signal_name=STRATEGY,
        source_time_column="band_signal_bar_open",
    )
    project_completed_entries(
        output,
        state,
        signal_hours=SIGNAL_HOURS,
        execution_minutes=EXECUTION_MINUTES,
        state_stop_column="stop_price",
        source_time_column="band_signal_bar_open",
        label="hourly band re-entry",
    )
    state.index = (
        state.index
        + pd.Timedelta(hours=SIGNAL_HOURS)
        - pd.Timedelta(minutes=EXECUTION_MINUTES)
    )
    for side in ("long", "short"):
        output[f"{side}_exit"] |= state[f"{side}_exit"].reindex(
            output.index, fill_value=False
        )
    for column in ("band_mean", "band_lower", "band_upper", "atr"):
        output[column] = state[column].reindex(output.index)
    return output


def _hourly_state(frame: pd.DataFrame) -> pd.DataFrame:
    segments = contiguous_segment_ids(frame.index, pd.Timedelta(hours=SIGNAL_HOURS))
    grouped = frame.close.groupby(segments, sort=False)
    mean = grouped.transform(lambda values: values.rolling(PERIOD).mean())
    deviation = grouped.transform(lambda values: values.rolling(PERIOD).std(ddof=0))
    lower, upper = (
        mean - BAND_DEVIATIONS * deviation,
        mean + BAND_DEVIATIONS * deviation,
    )
    atr = segmented_wilder_rma(raw_true_range(frame, segments), segments, PERIOD)
    adjacent = frame.index.to_series().diff().eq(pd.Timedelta(hours=SIGNAL_HOURS))
    warmed = adjacent & np.isfinite(atr)
    long = (
        warmed
        & frame.close.shift(1).lt(lower.shift(1))
        & frame.close.ge(lower)
        & frame.close.lt(mean)
    )
    short = (
        warmed
        & frame.close.shift(1).gt(upper.shift(1))
        & frame.close.le(upper)
        & frame.close.gt(mean)
    )
    stop = (frame.close - ATR_MULTIPLE * atr).where(long)
    stop = stop.where(~short, frame.close + ATR_MULTIPLE * atr)
    return pd.DataFrame(
        {
            "long_entry": long,
            "short_entry": short,
            "stop_price": stop,
            "long_exit": frame.close.ge(mean),
            "short_exit": frame.close.le(mean),
            "band_mean": mean,
            "band_lower": lower,
            "band_upper": upper,
            "atr": atr,
        },
        index=frame.index,
    )
