"""Causal completed-4h Donchian breakouts with ATR structural stops."""

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
class DonchianAtrBreakoutConfig:
    """Immutable parameters for the V75 channel-breakout contract."""

    entry_channel_bars: int = 20
    exit_channel_bars: int = 10
    atr_period: int = 20
    atr_multiple: float = 2.0
    signal_hours: int = 4
    execution_minutes: int = 15

    def __post_init__(self) -> None:
        """Reject incoherent channel, volatility, or clock parameters."""
        periods = (
            self.entry_channel_bars,
            self.exit_channel_bars,
            self.atr_period,
        )
        if any(isinstance(value, bool) or value < 1 for value in periods):
            raise ValueError("Donchian and ATR periods must be positive integers")
        if self.entry_channel_bars < 2:
            raise ValueError("entry channel must contain at least two bars")
        if self.exit_channel_bars >= self.entry_channel_bars:
            raise ValueError("exit channel must be shorter than entry channel")
        if not math.isfinite(self.atr_multiple) or self.atr_multiple <= 0.0:
            raise ValueError("ATR multiple must be positive and finite")
        if self.signal_hours != 4 or self.execution_minutes != 15:
            raise ValueError("V75 requires completed 4h signals and 15m execution")


def build_donchian_atr_breakout_state(
    signal_bars: pd.DataFrame,
    config: DonchianAtrBreakoutConfig | None = None,
) -> pd.DataFrame:
    """Return prior-channel breakouts, side exits, ATR, and entry stops."""
    cfg = config or DonchianAtrBreakoutConfig()
    frame = validated_ohlc_bars(signal_bars, label="Donchian/ATR breakout")
    segments = contiguous_segment_ids(
        frame.index,
        pd.Timedelta(hours=cfg.signal_hours),
    )
    close = frame["close"].to_numpy(dtype=np.float64)
    entry_high = _prior_extreme(
        frame["high"].to_numpy(dtype=np.float64),
        segments,
        cfg.entry_channel_bars,
        "max",
    )
    entry_low = _prior_extreme(
        frame["low"].to_numpy(dtype=np.float64),
        segments,
        cfg.entry_channel_bars,
        "min",
    )
    exit_high = _prior_extreme(
        frame["high"].to_numpy(dtype=np.float64),
        segments,
        cfg.exit_channel_bars,
        "max",
    )
    exit_low = _prior_extreme(
        frame["low"].to_numpy(dtype=np.float64),
        segments,
        cfg.exit_channel_bars,
        "min",
    )
    long_breakout = close > entry_high
    short_breakout = close < entry_low
    long_entry = _fresh_onset(long_breakout, segments)
    short_entry = _fresh_onset(short_breakout, segments)
    atr = segmented_wilder_rma(
        raw_true_range(frame, segments),
        segments,
        cfg.atr_period,
    )
    stop = _entry_stops(
        close,
        atr,
        long_entry,
        short_entry,
        cfg.atr_multiple,
    )
    return pd.DataFrame(
        {
            "prior_entry_high": entry_high,
            "prior_entry_low": entry_low,
            "prior_exit_high": exit_high,
            "prior_exit_low": exit_low,
            "atr": atr,
            "long_entry": long_entry,
            "short_entry": short_entry,
            "long_exit": close < exit_low,
            "short_exit": close > exit_high,
            "stop_price": stop,
        },
        index=frame.index,
    )


def build_donchian_atr_breakout_signals(
    execution_bars: pd.DataFrame,
    config: DonchianAtrBreakoutConfig | None = None,
) -> pd.DataFrame:
    """Project completed 4h channel decisions for next-15m-open execution."""
    cfg = config or DonchianAtrBreakoutConfig()
    frame = validated_ohlc_bars(execution_bars, label="Donchian/ATR breakout")
    signal_bars = complete_resampled_ohlc(
        frame,
        source_minutes=cfg.execution_minutes,
        target_hours=cfg.signal_hours,
    )
    state = build_donchian_atr_breakout_state(signal_bars, cfg)
    output = empty_directional_signals(
        frame.index,
        signal_name="completed_4h_donchian_20_10_atr20_stop_v1",
        source_time_column="donchian_signal_bar_open",
    )
    project_completed_entries(
        output,
        state,
        signal_hours=cfg.signal_hours,
        execution_minutes=cfg.execution_minutes,
        state_stop_column="stop_price",
        source_time_column="donchian_signal_bar_open",
        label="Donchian/ATR breakout signal",
    )
    _project_channel_exits(output, state, cfg)
    return output


def _prior_extreme(
    values: NDArray[np.float64],
    segments: NDArray[np.int64],
    period: int,
    operation: str,
) -> NDArray[np.float64]:
    result = np.full(len(values), np.nan, dtype=np.float64)
    for segment in np.unique(segments):
        positions = np.flatnonzero(segments == segment)
        series = pd.Series(values[positions])
        rolling = series.rolling(period, min_periods=period)
        extreme = rolling.max() if operation == "max" else rolling.min()
        result[positions] = extreme.shift(1).to_numpy(dtype=np.float64)
    return result


def _fresh_onset(
    active: NDArray[np.bool_],
    segments: NDArray[np.int64],
) -> NDArray[np.bool_]:
    result = np.zeros(len(active), dtype=np.bool_)
    for position in range(1, len(active)):
        same_segment = segments[position] == segments[position - 1]
        result[position] = (
            same_segment and active[position] and not active[position - 1]
        )
    return result


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


def _project_channel_exits(
    output: pd.DataFrame,
    state: pd.DataFrame,
    config: DonchianAtrBreakoutConfig,
) -> None:
    telemetry = ("prior_entry_high", "prior_exit_low", "atr")
    for column in telemetry:
        output[column] = np.nan
    for signal_time, row in state.iterrows():
        decision_time = (
            pd.Timestamp(signal_time)
            + pd.Timedelta(hours=config.signal_hours)
            - pd.Timedelta(minutes=config.execution_minutes)
        )
        if decision_time not in output.index:
            raise RuntimeError("completed Donchian bar is missing its decision row")
        for column in telemetry:
            output.loc[decision_time, column] = float(row[column])
        if bool(row["long_exit"]):
            output.loc[decision_time, "long_exit"] = True
        if bool(row["short_exit"]):
            output.loc[decision_time, "short_exit"] = True
