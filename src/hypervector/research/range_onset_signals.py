"""Frozen causal signal contract for the SOL range-onset challenger."""

from __future__ import annotations

from functools import partial

import pandas as pd

from hypervector.regime.composite import classify_multitimeframe
from hypervector.research.shared_strategy_signals import (
    build_strategy_pair_signals_on_timeframe_from_specs,
)
from hypervector.strategies.registry import StrategySpec


def _sma_cross_signals(
    df: pd.DataFrame, *, fast: int, slow: int, direction: str
) -> tuple[pd.Series, pd.Series, str]:
    """Enter on the fast/slow SMA cross in ``direction``; exit on the opposite cross."""
    if fast >= slow:
        raise ValueError("fast must be < slow")
    close = df["close"].astype(float)
    ma_f = close.rolling(fast, min_periods=fast).mean()
    ma_s = close.rolling(slow, min_periods=slow).mean()
    cross_up = ((ma_f > ma_s) & (ma_f.shift(1) <= ma_s.shift(1))).fillna(False)
    cross_dn = ((ma_f < ma_s) & (ma_f.shift(1) >= ma_s.shift(1))).fillna(False)
    if direction == "long":
        return cross_up.astype(bool), cross_dn.astype(bool), direction
    return cross_dn.astype(bool), cross_up.astype(bool), direction


_SMA_CROSS_LONG = StrategySpec(
    name="ma_cross_long",
    role="uptrend",
    param_grid={},
    build_signals=partial(_sma_cross_signals, direction="long"),
)
_SMA_CROSS_SHORT = StrategySpec(
    name="ma_cross_short",
    role="downtrend",
    param_grid={},
    build_signals=partial(_sma_cross_signals, direction="short"),
)


def build_range_onset_signals(
    bars: pd.DataFrame,
    *,
    timeframe: str = "1h",
    regimes: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Retain completed SMA10/30 crosses in 5m RANGE or BREAKOUT state."""
    signals = build_strategy_pair_signals_on_timeframe_from_specs(
        bars,
        timeframe=timeframe,
        long_spec=_SMA_CROSS_LONG,
        short_spec=_SMA_CROSS_SHORT,
        long_params={"fast": 10, "slow": 30},
        short_params={"fast": 10, "slow": 30},
    )
    regime_frame = regimes if regimes is not None else classify_multitimeframe(bars)
    if not regime_frame.index.equals(bars.index) or "state_5m" not in regime_frame:
        raise ValueError("range-onset regimes require aligned state_5m telemetry")
    allowed = regime_frame["state_5m"].isin(["RANGE", "BREAKOUT"])
    state = _completed_sma_state(bars, timeframe)
    result = signals.copy()
    result["raw_long_cross"] = signals["long_entry"].astype(bool)
    result["raw_short_cross"] = signals["short_entry"].astype(bool)
    result["long_entry"] = signals["long_entry"].astype(bool) & allowed
    result["short_entry"] = signals["short_entry"].astype(bool) & allowed
    result["structural_direction"] = state["direction"]
    result["sma_fast"] = state["fast"]
    result["sma_slow"] = state["slow"]
    result["sma_gap_bps"] = state["gap_bps"]
    result["regime_admitted"] = allowed.astype(bool)
    result["source_timeframe"] = timeframe
    return result


def _completed_sma_state(bars: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Project completed SMA relation and exact cross distance to minute bars."""
    delta = pd.Timedelta(timeframe)
    minute = pd.Timedelta(minutes=1)
    if delta < minute or delta % minute != pd.Timedelta(0):
        raise ValueError("range-onset timeframe must be whole positive minutes")
    ratio = int(delta / minute)
    grouped = (
        bars["close"]
        .astype(float)
        .resample(
            timeframe,
            label="left",
            closed="left",
        )
    )
    complete_close = grouped.last().loc[grouped.size().eq(ratio)].dropna()
    fast = complete_close.rolling(10, min_periods=10).mean()
    slow = complete_close.rolling(30, min_periods=30).mean()
    direction = pd.Series("neutral", index=complete_close.index, dtype="object")
    direction.loc[fast > slow] = "long"
    direction.loc[fast < slow] = "short"
    gap = (fast - slow) / slow * 10_000.0
    hourly = pd.DataFrame(
        {"direction": direction, "fast": fast, "slow": slow, "gap_bps": gap}
    )
    projected = pd.DataFrame(index=bars.index, columns=hourly.columns)
    endpoints = hourly.index + delta - minute
    valid = endpoints.isin(projected.index)
    projected.loc[endpoints[valid], :] = hourly.loc[valid].to_numpy()
    projected = projected.ffill()
    projected["direction"] = projected["direction"].fillna("neutral")
    return projected
