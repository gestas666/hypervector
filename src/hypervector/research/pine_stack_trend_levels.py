"""Causal backend translation of ChartPrime Trend Levels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from hypervector.research.pine_stack_native_bars import validated_native_bars

AmbiguityPolicy = Literal["source_exact", "hold"]


@dataclass(frozen=True)
class TrendLevelsConfig:
    """Structural lookback and simultaneous-extreme behavior."""

    lookback: int = 30
    ambiguity_policy: AmbiguityPolicy = "hold"

    def __post_init__(self) -> None:
        """Reject invalid lookbacks and unknown ambiguity behavior."""
        if isinstance(self.lookback, bool) or self.lookback < 2:
            raise ValueError("Trend Levels lookback must be at least two bars")
        if self.ambiguity_policy not in {"source_exact", "hold"}:
            raise ValueError("Trend Levels ambiguity policy is unknown")


def build_trend_levels(
    bars: pd.DataFrame,
    *,
    bar_minutes: int,
    config: TrendLevelsConfig | None = None,
) -> pd.DataFrame:
    """Return completed structural state, episode levels, and ambiguity telemetry."""
    cfg = config or TrendLevelsConfig()
    frame = validated_native_bars(bars, bar_minutes=bar_minutes)
    highs = frame["high"].astype(float)
    lows = frame["low"].astype(float)
    rolling_high = highs.rolling(cfg.lookback, min_periods=cfg.lookback).max()
    rolling_low = lows.rolling(cfg.lookback, min_periods=cfg.lookback).min()
    high_event = highs.eq(rolling_high) & rolling_high.notna()
    low_event = lows.eq(rolling_low) & rolling_low.notna()
    ambiguous = high_event & low_event
    states, episode_bars, episode_high, episode_low, delta = _episode_state(
        frame, high_event.to_numpy(), low_event.to_numpy(), cfg.ambiguity_policy
    )
    result = frame.loc[:, ["bar_open_at"]].copy()
    result["decision_time_utc"] = result["bar_open_at"] + pd.Timedelta(
        minutes=bar_minutes
    )
    result["trend_state"] = states
    result["episode_bars"] = episode_bars
    result["episode_high"] = episode_high
    result["episode_low"] = episode_low
    result["episode_mid"] = (episode_high + episode_low) / 2.0
    result.loc[result["episode_bars"].le(1), "episode_mid"] = np.nan
    result["close_location_delta_pct"] = delta
    result["ambiguous_extreme"] = ambiguous.to_numpy(dtype=np.bool_)
    result["ambiguity_policy"] = cfg.ambiguity_policy
    return result


def _episode_state(
    frame: pd.DataFrame,
    high_event: NDArray[np.bool_],
    low_event: NDArray[np.bool_],
    policy: AmbiguityPolicy,
) -> tuple[
    NDArray[np.int8],
    NDArray[np.int64],
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
]:
    rows = len(frame)
    states = np.zeros(rows, dtype=np.int8)
    durations = np.zeros(rows, dtype=np.int64)
    episode_high = np.full(rows, np.nan, dtype=np.float64)
    episode_low = np.full(rows, np.nan, dtype=np.float64)
    delta = np.full(rows, np.nan, dtype=np.float64)
    state = 0
    duration = count_up = count_down = 0
    current_high = current_low = np.nan
    for position in range(rows):
        next_state = _next_state(
            state, bool(high_event[position]), bool(low_event[position]), policy
        )
        if next_state == 0:
            continue
        changed = next_state != state
        state = next_state
        if changed:
            duration, count_up, count_down = 1, 0, 0
            current_high = float(frame.iloc[position]["high"])
            current_low = float(frame.iloc[position]["low"])
        else:
            duration += 1
            current_high = max(current_high, float(frame.iloc[position]["high"]))
            current_low = min(current_low, float(frame.iloc[position]["low"]))
        states[position] = state
        durations[position] = duration
        episode_high[position] = current_high
        episode_low[position] = current_low
        if duration > 1:
            midpoint = (current_high + current_low) / 2.0
            close = float(frame.iloc[position]["close"])
            count_up += int(close > midpoint)
            count_down += int(close < midpoint)
            total = count_up + count_down
            if total:
                delta[position] = (count_up - count_down) / total * 100.0
    return states, durations, episode_high, episode_low, delta


def _next_state(
    current: int,
    high_event: bool,
    low_event: bool,
    policy: AmbiguityPolicy,
) -> int:
    if high_event and low_event:
        return -1 if policy == "source_exact" else current
    if high_event:
        return 1
    if low_event:
        return -1
    return current
