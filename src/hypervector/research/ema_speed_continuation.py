"""Frozen causal signals for the 15-minute EMA-speed challenger."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd


_REQUIRED_COLUMNS = frozenset({"open", "high", "low", "close", "source_complete"})


@dataclass(frozen=True)
class EmaSpeedContinuationConfig:
    """Immutable first-pass parameters from the V57 preregistration."""

    symbols: tuple[str, ...] = ("BTC", "SOL")
    timeframe_minutes: int = 15
    ema_periods: tuple[int, int, int] = (5, 21, 55)
    stop_lookback_bars: int = 8
    maximum_stop_distance_bps: float = 80.0
    maximum_hold_bars: int = 16
    report_only: bool = True
    execution_authority: str = "none"

    def __post_init__(self) -> None:
        """Reject changes to the registered first-pass hypothesis."""
        if self.symbols != ("BTC", "SOL"):
            raise ValueError("frozen symbols must equal BTC and SOL")
        if self.timeframe_minutes != 15:
            raise ValueError("frozen timeframe must equal 15 minutes")
        if self.ema_periods != (5, 21, 55):
            raise ValueError("frozen EMA periods must equal 5, 21, and 55")
        if self.stop_lookback_bars != 8:
            raise ValueError("frozen stop lookback must equal eight bars")
        if not math.isclose(self.maximum_stop_distance_bps, 80.0):
            raise ValueError("frozen maximum stop distance must equal 80 bps")
        if self.maximum_hold_bars != 16:
            raise ValueError("frozen maximum hold must equal sixteen bars")
        if not self.report_only or self.execution_authority != "none":
            raise ValueError("EMA-speed research must remain report-only")


def build_ema_speed_signals(
    bars: pd.DataFrame,
    config: EmaSpeedContinuationConfig,
) -> pd.DataFrame:
    """Build gap-reset, completed-close entry and exit instructions."""
    market = _validated_bars(bars, config)
    fast, medium, slow = _ema_columns(market, config.ema_periods)
    close = market["close"].astype(float)
    ready = fast.notna() & medium.notna() & slow.notna()
    prior_ready = ready.shift(1, fill_value=False)
    long_cross = close.gt(fast) & close.shift(1).le(fast.shift(1))
    short_cross = close.lt(fast) & close.shift(1).ge(fast.shift(1))
    long_entry = ready & prior_ready & long_cross & fast.gt(medium) & medium.gt(slow)
    short_entry = ready & prior_ready & short_cross & fast.lt(medium) & medium.lt(slow)
    output = _base_output(market, fast, medium, slow, ready)
    output["long_entry"] = long_entry
    output["short_entry"] = short_entry
    output["long_exit"] = ready & close.lt(fast)
    output["short_exit"] = ready & close.gt(fast)
    output["stop_price"] = _stop_prices(market, long_entry, short_entry, config)
    output["long_signal_name"] = "ema5_speed_continuation_long@15m"
    output["short_signal_name"] = "ema5_speed_continuation_short@15m"
    return output


def _validated_bars(
    bars: pd.DataFrame,
    config: EmaSpeedContinuationConfig,
) -> pd.DataFrame:
    missing = sorted(_REQUIRED_COLUMNS.difference(bars.columns))
    if missing:
        raise ValueError(f"EMA-speed bars missing columns: {missing}")
    if len(bars) < max(config.ema_periods) + 2:
        raise ValueError("EMA-speed bars do not contain sufficient warmup")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("EMA-speed bars require an aware DatetimeIndex")
    if not bars.index.is_unique or not bars.index.is_monotonic_increasing:
        raise ValueError("EMA-speed bars require unique increasing timestamps")
    expected = pd.Timedelta(minutes=config.timeframe_minutes)
    if not bars.index.to_series().diff().dropna().eq(expected).all():
        raise ValueError("EMA-speed bars require exact 15-minute cadence")
    market = bars.copy()
    _validate_prices(market)
    if (
        not market["source_complete"]
        .map(lambda value: isinstance(value, (bool, np.bool_)))
        .all()
    ):
        raise ValueError("source_complete must contain booleans")
    return market


def _validate_prices(bars: pd.DataFrame) -> None:
    columns = ["open", "high", "low", "close"]
    prices = bars[columns].astype(float)
    complete = bars["source_complete"].astype(bool)
    complete_prices = prices.loc[complete].to_numpy(float)
    if not np.isfinite(complete_prices).all() or (complete_prices <= 0.0).any():
        raise ValueError("EMA-speed OHLC must be finite and positive")
    incomplete = prices.loc[~complete]
    valid_incomplete = incomplete.isna().all(axis=1) | np.isfinite(incomplete).all(
        axis=1
    )
    if not valid_incomplete.all():
        raise ValueError("incomplete EMA-speed OHLC must be all finite or all missing")
    observed = prices.loc[complete | prices.notna().all(axis=1)]
    if (observed <= 0.0).any().any():
        raise ValueError("EMA-speed observed OHLC must be positive")
    if (observed["high"] < observed.max(axis=1)).any() or (
        observed["low"] > observed.min(axis=1)
    ).any():
        raise ValueError("EMA-speed OHLC is internally inconsistent")


def _ema_columns(
    bars: pd.DataFrame,
    periods: tuple[int, int, int],
) -> tuple[pd.Series, pd.Series, pd.Series]:
    complete = bars["source_complete"].astype(bool)
    group = (~complete).cumsum()
    columns: list[pd.Series] = []
    for period in periods:
        values = (
            bars["close"]
            .where(complete)
            .groupby(group)
            .transform(
                lambda part: part.ewm(
                    span=period, adjust=False, min_periods=period
                ).mean()
            )
        )
        columns.append(values.where(complete))
    return columns[0], columns[1], columns[2]


def _base_output(
    bars: pd.DataFrame,
    fast: pd.Series,
    medium: pd.Series,
    slow: pd.Series,
    ready: pd.Series,
) -> pd.DataFrame:
    output = pd.DataFrame(index=bars.index)
    output["ema_5"] = fast
    output["ema_21"] = medium
    output["ema_55"] = slow
    output["signal_state"] = np.where(
        ~bars["source_complete"].astype(bool),
        "source_incomplete",
        np.where(ready, "ready", "warming_after_gap"),
    )
    return output


def _stop_prices(
    bars: pd.DataFrame,
    long_entry: pd.Series,
    short_entry: pd.Series,
    config: EmaSpeedContinuationConfig,
) -> pd.Series:
    stop = pd.Series(np.nan, index=bars.index, dtype=float)
    fraction = config.maximum_stop_distance_bps / 10_000.0
    prior_low = bars["low"].shift(1).rolling(config.stop_lookback_bars).min()
    prior_high = bars["high"].shift(1).rolling(config.stop_lookback_bars).max()
    long_clamp = bars["close"] * (1.0 - fraction)
    short_clamp = bars["close"] * (1.0 + fraction)
    stop.loc[long_entry] = np.maximum(
        prior_low.loc[long_entry], long_clamp.loc[long_entry]
    )
    stop.loc[short_entry] = np.minimum(
        prior_high.loc[short_entry], short_clamp.loc[short_entry]
    )
    return stop
