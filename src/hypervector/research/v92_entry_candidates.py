"""Frozen causal entry candidates; no execution clients or live authority."""

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
from hypervector.research.completed_signal_projection import empty_directional_signals
from hypervector.research.donchian_atr_breakout_signals import (
    DonchianAtrBreakoutConfig,
    build_donchian_atr_breakout_state,
)

FAST_EMA = 21
SLOW_EMA = 55
ATR_PERIOD = 20
ATR_STOP_MULTIPLE = 2.0
MAX_EXTENSION_ATR = 1.0
SOURCE_MINUTES = 15
SIGNAL_HOURS = 1


def build_v92_signals(bars: pd.DataFrame, candidate: str) -> pd.DataFrame:
    """Project completed hourly evidence on its last quarter for next-open fills."""
    if candidate not in {"donchian", "donchian_bounded", "trend"}:
        raise ValueError(f"unknown V92 candidate: {candidate}")
    frame = validated_ohlc_bars(bars, label="V92 entry")
    if not frame.index.floor("15min").equals(frame.index):
        raise ValueError("V92 requires aligned 15-minute source bars")
    hourly = complete_resampled_ohlc(
        frame, source_minutes=SOURCE_MINUTES, target_hours=SIGNAL_HOURS
    )
    state = (
        _trend_state(hourly)
        if candidate == "trend"
        else _donchian_state(hourly, candidate)
    )
    output = empty_directional_signals(
        frame.index,
        signal_name=f"v92_{candidate}_v1",
        source_time_column="signal_bar_open",
    )
    for column in ("atr", "entry_extension_atr", "ema_fast", "ema_slow"):
        output[column] = np.nan
    output["entry_rejected_extension"] = False
    if state.empty:
        return output
    decision = state.index + pd.Timedelta(minutes=45)
    for column in (
        "long_entry",
        "short_entry",
        "long_exit",
        "short_exit",
        "stop_price",
        "atr",
        "entry_extension_atr",
        "ema_fast",
        "ema_slow",
        "entry_rejected_extension",
    ):
        if column in state:
            output.loc[decision, column] = state[column].to_numpy()
    output.loc[decision, "signal_bar_open"] = state.index
    output.loc[output.long_entry, "entry_direction"] = "long"
    output.loc[output.short_entry, "entry_direction"] = "short"
    return output


def _donchian_state(hourly: pd.DataFrame, candidate: str) -> pd.DataFrame:
    if len(hourly) < 2:
        return pd.DataFrame()
    state = build_donchian_atr_breakout_state(
        hourly, DonchianAtrBreakoutConfig(signal_hours=1)
    )
    long, short = state.long_entry.copy(), state.short_entry.copy()
    state["short_exit"] |= long
    state["long_exit"] |= short
    extension = pd.Series(np.nan, index=hourly.index)
    extension.loc[long] = (hourly.close - state.prior_entry_high).loc[
        long
    ] / state.atr.loc[long]
    extension.loc[short] = (state.prior_entry_low - hourly.close).loc[
        short
    ] / state.atr.loc[short]
    state["entry_extension_atr"] = extension
    rejected = (
        extension.gt(MAX_EXTENSION_ATR) if candidate == "donchian_bounded" else False
    )
    state["entry_rejected_extension"] = rejected
    valid = np.isfinite(state.stop_price) & ~state.entry_rejected_extension
    state["long_entry"] &= valid
    state["short_entry"] &= valid
    state.loc[~(state.long_entry | state.short_entry), "stop_price"] = np.nan
    return state


def _trend_state(hourly: pd.DataFrame) -> pd.DataFrame:
    if len(hourly) < 2:
        return pd.DataFrame()
    segments = contiguous_segment_ids(hourly.index, pd.Timedelta(hours=1))
    close = hourly.close
    fast = close.groupby(segments).transform(
        lambda x: x.ewm(span=FAST_EMA, adjust=False, min_periods=FAST_EMA).mean()
    )
    slow = close.groupby(segments).transform(
        lambda x: x.ewm(span=SLOW_EMA, adjust=False, min_periods=SLOW_EMA).mean()
    )
    atr = pd.Series(
        segmented_wilder_rma(raw_true_range(hourly, segments), segments, ATR_PERIOD),
        index=hourly.index,
    )
    ready = np.isfinite(atr) & atr.gt(0) & np.isfinite(slow)
    long, short = (
        ready & fast.gt(slow) & close.gt(fast),
        ready & fast.lt(slow) & close.lt(fast),
    )
    stop = pd.Series(np.nan, index=hourly.index)
    stop.loc[long] = (close - ATR_STOP_MULTIPLE * atr).loc[long]
    stop.loc[short] = (close + ATR_STOP_MULTIPLE * atr).loc[short]
    return pd.DataFrame(
        {
            "long_entry": long,
            "short_entry": short,
            "long_exit": ready & close.lt(fast),
            "short_exit": ready & close.gt(fast),
            "stop_price": stop,
            "atr": atr,
            "ema_fast": fast,
            "ema_slow": slow,
        }
    )
