"""Causal HIP-3 breakout signals confirmed by visible-book pressure."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Hip3BreakoutPressureConfig:
    """Parameters for symmetric close-known breakout-pressure decisions."""

    breakout_lookback_bars: int
    fast_ema: int
    slow_ema: int
    minimum_abs_imbalance: float
    maximum_stop_bps: float

    def __post_init__(self) -> None:
        """Reject ambiguous or non-finite research configurations."""
        _require_positive_integer(self.breakout_lookback_bars, "breakout_lookback_bars")
        _require_positive_integer(self.fast_ema, "fast_ema")
        _require_positive_integer(self.slow_ema, "slow_ema")
        if self.fast_ema >= self.slow_ema:
            raise ValueError("fast_ema must be less than slow_ema")
        if (
            not math.isfinite(self.minimum_abs_imbalance)
            or not 0.0 < (self.minimum_abs_imbalance) <= 1.0
        ):
            raise ValueError("minimum_abs_imbalance must be in (0, 1]")
        if not math.isfinite(self.maximum_stop_bps) or self.maximum_stop_bps <= 0.0:
            raise ValueError("maximum_stop_bps must be finite and positive")


def build_breakout_pressure_signals(
    bars: pd.DataFrame,
    config: Hip3BreakoutPressureConfig,
    *,
    timeframe: str = "15m",
) -> pd.DataFrame:
    """Build gap-reset, next-bar-eligible long and short signal instructions."""
    _validate_bars(bars)
    _validate_timeframe(timeframe)
    segment_ids = bars["gap_before_bars"].gt(0).cumsum().astype(int)
    prior_high = _rolling_prior(
        bars["high"], segment_ids, config.breakout_lookback_bars, "max"
    )
    prior_low = _rolling_prior(
        bars["low"], segment_ids, config.breakout_lookback_bars, "min"
    )
    fast_ema = _segmented_ema(bars["close"], segment_ids, config.fast_ema)
    slow_ema = _segmented_ema(bars["close"], segment_ids, config.slow_ema)
    pressure = bars["decision_imbalance_10"].astype(float)
    long_raw = (
        bars["close"].gt(prior_high)
        & fast_ema.gt(slow_ema)
        & pressure.ge(config.minimum_abs_imbalance)
    )
    short_raw = (
        bars["close"].lt(prior_low)
        & fast_ema.lt(slow_ema)
        & pressure.le(-config.minimum_abs_imbalance)
    )
    long_entry = _fresh_onset(long_raw, segment_ids)
    short_entry = _fresh_onset(short_raw, segment_ids)
    recovery = bars["gap_before_bars"].gt(0)
    output = _signal_frame(bars.index, long_entry, short_entry, timeframe)
    output["stop_price"] = _stop_prices(
        bars["close"], prior_high, prior_low, long_entry, short_entry, config
    )
    output["long_exit"] = fast_ema.le(slow_ema).fillna(False) | recovery
    output["short_exit"] = fast_ema.ge(slow_ema).fillna(False) | recovery
    output["gap_recovery_exit"] = recovery
    output["entry_expired_across_gap"] = False
    output["prior_breakout_high"] = prior_high
    output["prior_breakout_low"] = prior_low
    output["fast_ema"] = fast_ema
    output["slow_ema"] = slow_ema
    output["decision_imbalance_10"] = pressure
    output["source_segment_id"] = segment_ids
    output["execution_authority"] = "none"
    return output


def _signal_frame(
    index: pd.DatetimeIndex,
    long_entry: pd.Series,
    short_entry: pd.Series,
    timeframe: str,
) -> pd.DataFrame:
    direction = pd.Series([None] * len(index), index=index, dtype=object)
    direction.loc[long_entry] = "long"
    direction.loc[short_entry] = "short"
    output = pd.DataFrame(index=index)
    output["long_entry"] = long_entry.astype(bool)
    output["short_entry"] = short_entry.astype(bool)
    output["entry_direction"] = direction
    output["breakout_side"] = direction.copy()
    output["signal_name"] = direction.map(
        {
            "long": f"hip3_breakout_pressure_long@{timeframe}",
            "short": f"hip3_breakout_pressure_short@{timeframe}",
        }
    )
    output["target_price"] = float("nan")
    return output


def _validate_timeframe(timeframe: str) -> None:
    if timeframe not in {"5m", "15m"}:
        raise ValueError("HIP-3 breakout timeframe must be 5m or 15m")


def _stop_prices(
    close: pd.Series,
    prior_high: pd.Series,
    prior_low: pd.Series,
    long_entry: pd.Series,
    short_entry: pd.Series,
    config: Hip3BreakoutPressureConfig,
) -> pd.Series:
    stop_fraction = config.maximum_stop_bps / 10_000.0
    fixed_long = close * (1.0 - stop_fraction)
    fixed_short = close * (1.0 + stop_fraction)
    stops = pd.Series(float("nan"), index=close.index, dtype=float)
    stops.loc[long_entry] = pd.concat([fixed_long, prior_low], axis=1).max(axis=1)
    stops.loc[short_entry] = pd.concat([fixed_short, prior_high], axis=1).min(axis=1)
    return stops


def _rolling_prior(
    values: pd.Series,
    segment_ids: pd.Series,
    window: int,
    operation: str,
) -> pd.Series:
    grouped = values.astype(float).groupby(segment_ids, sort=False)
    if operation == "max":
        return grouped.transform(
            lambda segment: segment.shift(1).rolling(window, min_periods=window).max()
        )
    return grouped.transform(
        lambda segment: segment.shift(1).rolling(window, min_periods=window).min()
    )


def _segmented_ema(
    values: pd.Series,
    segment_ids: pd.Series,
    span: int,
) -> pd.Series:
    return (
        values.astype(float)
        .groupby(segment_ids, sort=False)
        .transform(
            lambda segment: segment.ewm(
                span=span,
                adjust=False,
                min_periods=span,
            ).mean()
        )
    )


def _fresh_onset(raw: pd.Series, segment_ids: pd.Series) -> pd.Series:
    prior = raw.groupby(segment_ids, sort=False).shift(1, fill_value=False)
    return raw & ~prior.astype(bool)


def _validate_bars(bars: pd.DataFrame) -> None:
    required = {
        "open",
        "high",
        "low",
        "close",
        "decision_imbalance_10",
        "gap_before_bars",
    }
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"HIP-3 breakout bars missing columns: {sorted(missing)}")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("HIP-3 breakout bars require a timezone-aware index")
    if bars.empty or not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError("HIP-3 breakout bars require ordered unique rows")
    _validate_numeric_bars(bars)


def _validate_numeric_bars(bars: pd.DataFrame) -> None:
    prices = bars.loc[:, ["open", "high", "low", "close"]].astype(float)
    if not prices.map(math.isfinite).to_numpy().all() or prices.le(0.0).any().any():
        raise ValueError("HIP-3 breakout OHLC must be finite and positive")
    if prices["high"].lt(prices[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("HIP-3 breakout high values are inconsistent")
    if prices["low"].gt(prices[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("HIP-3 breakout low values are inconsistent")
    pressure = pd.to_numeric(bars["decision_imbalance_10"], errors="raise")
    if (
        pressure.isna().any()
        or not pressure.map(math.isfinite).all()
        or pressure.abs().gt(1.0).any()
    ):
        raise ValueError("decision_imbalance_10 must be finite and within [-1, 1]")
    gaps = pd.to_numeric(bars["gap_before_bars"], errors="raise")
    if gaps.isna().any() or gaps.lt(0).any() or not gaps.mod(1).eq(0).all():
        raise ValueError("gap_before_bars must contain non-negative integers")


def _require_positive_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
