"""Causal feature construction for 5m execution and 15m context research."""

from __future__ import annotations

from dataclasses import dataclass, fields

import numpy as np
import pandas as pd

from hypervector.research.low_tf_multi_asset_contract import complete_ohlcv_bars
from hypervector.research.low_tf_rsi_divergence import (
    confirmed_regular_rsi_divergence,
)
from hypervector.strategies.indicators import atr, bbwp, ema, pmarp, rsi


@dataclass(frozen=True)
class LowTfFeatureConfig:
    """Predeclared feature lengths for the low-timeframe candidate cohort."""

    range_lookback: int = 240
    breakout_lookback: int = 120
    ema_fast: int = 21
    ema_slow: int = 55
    bbwp_length: int = 20
    bbwp_lookback: int = 240
    bbwp_signal: int = 5
    rsi_length: int = 14
    rsi_signal: int = 7
    pmarp_ema: int = 21
    pmarp_lookback: int = 350
    pmarp_signal: int = 7
    atr_length: int = 14

    def __post_init__(self) -> None:
        """Require every causal lookback and smoothing length to be positive."""
        invalid = [
            field.name
            for field in fields(self)
            if isinstance(getattr(self, field.name), bool)
            or not isinstance(getattr(self, field.name), int)
            or getattr(self, field.name) <= 0
        ]
        if invalid:
            raise ValueError(f"feature lengths must be positive integers: {invalid}")
        if self.ema_fast >= self.ema_slow:
            raise ValueError("ema_fast must be below ema_slow")


def build_low_tf_features(
    bars: pd.DataFrame,
    config: LowTfFeatureConfig | None = None,
) -> pd.DataFrame:
    """Return one append-invariant feature row per completed 5m execution bar."""
    cfg = config or LowTfFeatureConfig()
    execution = _validated_execution_bars(bars)
    close = execution["close"].astype(float)
    frame = execution.copy()
    frame = _attach_structural_features(frame, cfg)
    frame = _attach_execution_indicators(frame, close, cfg)
    context = _context_features(execution, cfg)
    return _align_completed_context(frame, context)


def _validated_execution_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Validate exact 5m UTC bars through the shared aggregation contract."""
    if "bar_open_at" not in bars:
        raise ValueError("execution bars missing bar_open_at")
    source = bars.rename(columns={"bar_open_at": "timestamp"})
    validated = complete_ohlcv_bars(source, source_minutes=5, bar_minutes=5)
    original_times = pd.DatetimeIndex(bars["bar_open_at"])
    validated_times = pd.DatetimeIndex(validated["bar_open_at"])
    if not original_times.equals(validated_times):
        raise ValueError("execution bars must align to complete 5m UTC buckets")
    return validated


def _attach_structural_features(
    frame: pd.DataFrame, config: LowTfFeatureConfig
) -> pd.DataFrame:
    """Attach completed-prior-window structural boundaries and widths."""
    output = frame.copy()
    output["range_high_240"] = _prior_rolling(
        output["high"], config.range_lookback, "max"
    )
    output["range_low_240"] = _prior_rolling(
        output["low"], config.range_lookback, "min"
    )
    output["range_midpoint_240"] = (
        output["range_high_240"] + output["range_low_240"]
    ) / 2.0
    output["range_width_bps"] = _distance_bps(
        output["range_high_240"],
        output["range_low_240"],
        output["range_midpoint_240"],
    )
    output["breakout_high_120"] = _prior_rolling(
        output["high"], config.breakout_lookback, "max"
    )
    output["breakout_low_120"] = _prior_rolling(
        output["low"], config.breakout_lookback, "min"
    )
    return output


def _attach_execution_indicators(
    frame: pd.DataFrame,
    close: pd.Series,
    config: LowTfFeatureConfig,
) -> pd.DataFrame:
    """Attach causal 5m trend, volatility, momentum, and range features."""
    output = frame.copy()
    output["ema_fast_5m"] = ema(close, config.ema_fast)
    output["ema_slow_5m"] = ema(close, config.ema_slow)
    percentile, signal = bbwp(
        close,
        bb_length=config.bbwp_length,
        lookback=config.bbwp_lookback,
        signal_sma=config.bbwp_signal,
    )
    output["bbwp_percentile"] = percentile
    output["bbwp_signal"] = signal
    output["rsi"] = rsi(close, config.rsi_length)
    output["rsi_signal"] = ema(output["rsi"], config.rsi_signal)
    divergence = _completed_rsi_divergence(output)
    output["rsi_bearish_divergence"] = divergence["rsi_bearish_divergence"]
    output["rsi_bullish_divergence"] = divergence["rsi_bullish_divergence"]
    output["pmarp"] = pmarp(
        close,
        ema_length=config.pmarp_ema,
        lookback=config.pmarp_lookback,
    )
    output["pmarp_signal"] = ema(output["pmarp"], config.pmarp_signal)
    output["atr"] = atr(output["high"], output["low"], close, config.atr_length)
    return output


def _completed_rsi_divergence(frame: pd.DataFrame) -> pd.DataFrame:
    """Return confirmed divergence events after the leading RSI warmup."""
    valid = frame["rsi"].notna()
    result = pd.DataFrame(
        {
            "rsi_bearish_divergence": False,
            "rsi_bullish_divergence": False,
        },
        index=frame.index,
    )
    if not valid.any():
        return result
    first = int(np.flatnonzero(valid.to_numpy())[0])
    if not valid.iloc[first:].all():
        raise ValueError("RSI contains a non-leading missing value")
    calculated = confirmed_regular_rsi_divergence(
        frame.loc[valid, "high"],
        frame.loc[valid, "low"],
        frame.loc[valid, "rsi"],
    )
    result.loc[valid, list(calculated.columns)] = calculated
    return result.astype(bool)


def _context_features(
    execution: pd.DataFrame, config: LowTfFeatureConfig
) -> pd.DataFrame:
    """Build causal EMA direction from complete 15m context bars."""
    source = execution.rename(columns={"bar_open_at": "timestamp"})
    context = complete_ohlcv_bars(source, source_minutes=5, bar_minutes=15)
    close = context["close"].astype(float)
    fast = ema(close, config.ema_fast)
    slow = ema(close, config.ema_slow)
    direction = np.where(fast > slow, 1, np.where(fast < slow, -1, 0))
    return pd.DataFrame(
        {
            "context_bar_open_at": context["bar_open_at"],
            "context_available_at": context["bar_open_at"] + pd.Timedelta(minutes=15),
            "ema_fast_15m": fast,
            "ema_slow_15m": slow,
            "context_direction": direction.astype(np.int8),
            "context_fast_slope_bps": _slope_bps(fast),
        }
    )


def _align_completed_context(
    execution: pd.DataFrame, context: pd.DataFrame
) -> pd.DataFrame:
    """Align only context known at each 5m decision close and reject staleness."""
    left = execution.copy()
    left["decision_available_at"] = left["bar_open_at"] + pd.Timedelta(minutes=5)
    merged = pd.merge_asof(
        left,
        context,
        left_on="decision_available_at",
        right_on="context_available_at",
        direction="backward",
    )
    age = merged["decision_available_at"] - merged["context_available_at"]
    fresh = merged["context_available_at"].notna() & age.lt(pd.Timedelta(minutes=15))
    context_values = (
        "context_bar_open_at",
        "context_available_at",
        "ema_fast_15m",
        "ema_slow_15m",
        "context_fast_slope_bps",
    )
    merged.loc[~fresh, list(context_values)] = np.nan
    merged["context_direction"] = np.where(
        fresh, merged["context_direction"].fillna(0), 0
    ).astype(np.int8)
    return merged.drop(columns="decision_available_at")


def _prior_rolling(series: pd.Series, lookback: int, method: str) -> pd.Series:
    """Return a completed-prior-window minimum or maximum."""
    rolling = series.astype(float).shift(1).rolling(lookback, min_periods=lookback)
    if method == "max":
        return rolling.max()
    if method == "min":
        return rolling.min()
    raise ValueError(f"unsupported rolling method: {method}")


def _distance_bps(high: pd.Series, low: pd.Series, reference: pd.Series) -> pd.Series:
    """Return high-low distance in basis points around a positive reference."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return (high - low) / reference.replace(0.0, np.nan) * 10_000.0


def _slope_bps(series: pd.Series) -> pd.Series:
    """Return one completed-bar relative slope in basis points."""
    prior = series.shift(1).replace(0.0, np.nan)
    return (series / prior - 1.0) * 10_000.0
