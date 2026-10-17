"""Causal strategy hypotheses derived from supplied Pine and Apex references."""

from __future__ import annotations

from functools import partial
import math
from typing import Literal

import pandas as pd

from hypervector.strategies.indicators import bbwp, ema, zero_lag_trend_ohlc
from hypervector.strategies.registry import SignalBuilder, StrategySpec, register

Direction = Literal["long", "short"]
SignalResult = tuple[pd.Series, pd.Series, str]
LIQUIDITY_SWEEP_LOOKBACK = 20
LIQUIDITY_SWEEP_CLEARANCE_BPS = 2.0
LIQUIDITY_SWEEP_VOLUME_MULTIPLE = 1.2
LIQUIDITY_SWEEP_EMA_LENGTH = 55


def donchian_trend_signals(
    df: pd.DataFrame,
    *,
    direction: Direction,
    entry_lookback: int = 20,
    exit_lookback: int = 10,
    ema_length: int = 55,
) -> SignalResult:
    """Trade prior-range breakouts and exit on the shorter opposite channel."""
    _validate_lengths(entry_lookback, exit_lookback, ema_length)
    high, low, close, _ = _ohlcv(df)
    prior_high = high.shift(1).rolling(entry_lookback).max()
    prior_low = low.shift(1).rolling(entry_lookback).min()
    exit_high = high.shift(1).rolling(exit_lookback).max()
    exit_low = low.shift(1).rolling(exit_lookback).min()
    trend = ema(close, ema_length)
    if direction == "long":
        raw_entry = (close > prior_high) & (close > trend)
        exits = close < exit_low
    else:
        raw_entry = (close < prior_low) & (close < trend)
        exits = close > exit_high
    return _signals(raw_entry, exits, direction)


def squeeze_breakout_signals(
    df: pd.DataFrame,
    *,
    direction: Direction,
    range_lookback: int = 20,
    compression_lookback: int = 100,
    compression_window: int = 12,
    bbwp_max: float = 25.0,
    clearance_bps: float = 5.0,
    volume_multiple: float = 1.5,
    fast_ema: int = 21,
    slow_ema: int = 55,
    minimum_gap_bps: float = 1.0,
) -> SignalResult:
    """Trade volume-backed range breaks after recent BBWP compression."""
    _validate_squeeze(
        range_lookback,
        compression_lookback,
        compression_window,
        bbwp_max,
        clearance_bps,
        volume_multiple,
        fast_ema,
        slow_ema,
        minimum_gap_bps,
    )
    high, low, close, volume = _ohlcv(df)
    percentile, _ = bbwp(close, bb_length=20, lookback=compression_lookback)
    recent_compression = (
        percentile.shift(1).lt(bbwp_max).rolling(compression_window).max().eq(1.0)
    )
    prior_high = high.shift(1).rolling(range_lookback).max()
    prior_low = low.shift(1).rolling(range_lookback).min()
    mean_volume = volume.shift(1).rolling(range_lookback).mean()
    volume_ok = volume >= mean_volume * volume_multiple
    fast = ema(close, fast_ema)
    slow = ema(close, slow_ema)
    gap_bps = (fast - slow) / close * 10_000.0
    clearance = clearance_bps / 10_000.0
    if direction == "long":
        raw_entry = (
            recent_compression
            & volume_ok
            & (gap_bps >= minimum_gap_bps)
            & (close > prior_high * (1.0 + clearance))
        )
        exits = close < fast
    else:
        raw_entry = (
            recent_compression
            & volume_ok
            & (gap_bps <= -minimum_gap_bps)
            & (close < prior_low * (1.0 - clearance))
        )
        exits = close > fast
    return _signals(raw_entry, exits, direction)


def liquidity_sweep_signals(
    df: pd.DataFrame,
    *,
    direction: Direction,
    lookback: int = LIQUIDITY_SWEEP_LOOKBACK,
    clearance_bps: float = LIQUIDITY_SWEEP_CLEARANCE_BPS,
    volume_multiple: float = LIQUIDITY_SWEEP_VOLUME_MULTIPLE,
    ema_length: int = LIQUIDITY_SWEEP_EMA_LENGTH,
) -> SignalResult:
    """Trade wick sweeps that reclaim a prior range boundary with trend bias."""
    _positive_integer(lookback, "lookback")
    _positive_integer(ema_length, "ema_length")
    _nonnegative(clearance_bps, "clearance_bps")
    _positive(volume_multiple, "volume_multiple")
    high, low, close, volume = _ohlcv(df)
    prior_high = high.shift(1).rolling(lookback).max()
    prior_low = low.shift(1).rolling(lookback).min()
    mean_volume = volume.shift(1).rolling(lookback).mean()
    volume_ok = volume >= mean_volume * volume_multiple
    trend = ema(close, ema_length)
    clearance = clearance_bps / 10_000.0
    bull_sweep = (low < prior_low * (1.0 - clearance)) & (close > prior_low) & volume_ok
    bear_sweep = (
        (high > prior_high * (1.0 + clearance)) & (close < prior_high) & volume_ok
    )
    if direction == "long":
        raw_entry = bull_sweep & (close >= trend)
        exits = bear_sweep
    else:
        raw_entry = bear_sweep & (close <= trend)
        exits = bull_sweep
    return _signals(raw_entry, exits, direction)


def zero_lag_reclaim_signals(
    df: pd.DataFrame,
    *,
    direction: Direction,
    length: int = 70,
    multiplier: float = 1.2,
) -> SignalResult:
    """Trade basis reclaims inside an established zero-lag trend state."""
    _positive_integer(length, "length")
    _positive(multiplier, "multiplier")
    high, low, close, _ = _ohlcv(df)
    basis, trend = zero_lag_trend_ohlc(
        high,
        low,
        close,
        length=length,
        mult=multiplier,
    )
    if direction == "long":
        stable = trend.eq(1) & trend.shift(1).eq(1)
        raw_entry = stable & (close > basis) & (close.shift(1) <= basis.shift(1))
        exits = trend.eq(-1)
    else:
        stable = trend.eq(-1) & trend.shift(1).eq(-1)
        raw_entry = stable & (close < basis) & (close.shift(1) >= basis.shift(1))
        exits = trend.eq(1)
    return _signals(raw_entry, exits, direction)


def regime_trend_router_signals(
    df: pd.DataFrame,
    *,
    direction: Direction,
    context_timeframe: str = "4h",
) -> SignalResult:
    """Route trend setups only when local and completed HTF regimes align.

    Research bars with a RangeIndex are classified on their ``timestamp``
    column; signals keep the caller's index.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        if "timestamp" not in df.columns:
            raise ValueError(
                "regime router bars require a DatetimeIndex or timestamp column"
            )
        times = pd.DatetimeIndex(pd.to_datetime(df["timestamp"], utc=True))
        timed = df.set_axis(times.rename(None), axis=0)
        entries, exits, tag = regime_trend_router_signals(
            timed, direction=direction, context_timeframe=context_timeframe
        )
        return entries.set_axis(df.index), exits.set_axis(df.index), tag

    from hypervector.regime.classifier import classify_timeframe

    local = classify_timeframe(df)
    context = _completed_regime_context(df, context_timeframe)
    local_direction = _regime_direction(local)
    context_direction = _regime_direction(context)
    donchian_entry, _, _ = donchian_trend_signals(df, direction=direction)
    squeeze_entry, _, _ = squeeze_breakout_signals(df, direction=direction)
    zero_lag_entry, _, _ = zero_lag_reclaim_signals(df, direction=direction)
    aligned = local_direction.eq(direction) & context_direction.eq(direction)
    raw_entry = aligned & (donchian_entry | squeeze_entry | zero_lag_entry)
    opposite = "short" if direction == "long" else "long"
    exits = local_direction.eq(opposite) | context_direction.eq(opposite)
    return _signals(raw_entry, exits, direction)


def source_derived_builders() -> tuple[SignalBuilder, ...]:
    """Return every source-derived side builder for causality verification."""
    return tuple(
        partial(builder, direction=direction)
        for builder in (
            donchian_trend_signals,
            squeeze_breakout_signals,
            liquidity_sweep_signals,
            zero_lag_reclaim_signals,
            regime_trend_router_signals,
        )
        for direction in ("long", "short")
    )


def register_source_derived() -> None:
    """Register the four source-derived long/short research pairs."""
    definitions = (
        ("donchian_trend", donchian_trend_signals, "Prior-range trend breakout"),
        ("squeeze_breakout", squeeze_breakout_signals, "BBWP volume breakout"),
        ("liquidity_sweep", liquidity_sweep_signals, "Wick sweep and reclaim"),
        ("zero_lag_reclaim", zero_lag_reclaim_signals, "ZLEMA trend pullback"),
        (
            "regime_trend_router",
            regime_trend_router_signals,
            "Aligned local and completed HTF trend router",
        ),
    )
    for name, builder, description in definitions:
        _register_pair(name, builder, description)


def _register_pair(name: str, builder: SignalBuilder, description: str) -> None:
    for direction, role in (("long", "uptrend"), ("short", "downtrend")):
        register(
            StrategySpec(
                name=f"{name}_{direction}",
                role=role,
                param_grid={},
                build_signals=partial(builder, direction=direction),
                description=f"{description} {direction}",
            )
        )


def _completed_regime_context(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    from hypervector.regime.classifier import classify_timeframe

    interval = _regular_bar_interval(df.index)
    target = pd.Timedelta(timeframe)
    if target <= interval or target % interval != pd.Timedelta(0):
        raise ValueError("context timeframe must be a larger whole bar multiple")
    ratio = int(target / interval)
    grouped = df.resample(timeframe, label="left", closed="left")
    bars = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    bars = bars.loc[grouped.size().eq(ratio)].dropna()
    bars.index = bars.index + target - interval
    classified = classify_timeframe(bars)
    return classified.reindex(df.index, method="ffill")


def _regular_bar_interval(index: pd.DatetimeIndex) -> pd.Timedelta:
    if len(index) < 2 or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError(
            "strategy bars require at least two unique increasing timestamps"
        )
    differences = index.to_series().diff().iloc[1:]
    interval = differences.iloc[0]
    if differences.ne(interval).any():
        raise ValueError("strategy bars require regular cadence")
    return interval


def _regime_direction(classified: pd.DataFrame) -> pd.Series:
    from hypervector.regime.models import BreakoutDirection, PrimaryRegime

    primary = classified["primary_regime"]
    breakout = classified["breakout_direction"]
    direction = pd.Series(None, index=classified.index, dtype=object)
    direction = direction.mask(primary.eq(PrimaryRegime.TREND_UP.value), "long")
    direction = direction.mask(primary.eq(PrimaryRegime.TREND_DOWN.value), "short")
    is_breakout = primary.eq(PrimaryRegime.BREAKOUT.value)
    direction = direction.mask(
        is_breakout & breakout.eq(BreakoutDirection.UPWARD.value), "long"
    )
    return direction.mask(
        is_breakout & breakout.eq(BreakoutDirection.DOWNWARD.value), "short"
    )


def _ohlcv(
    df: pd.DataFrame,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    required = {"high", "low", "close", "volume"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"strategy bars missing required columns: {missing}")
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    volume = df["volume"].astype(float)
    return high, low, close, volume


def _signals(
    entries: pd.Series,
    exits: pd.Series,
    direction: Direction,
) -> SignalResult:
    entry_events = entries.fillna(False).astype(bool)
    entry_events &= ~entry_events.shift(1, fill_value=False)
    clean_exits = exits.fillna(False).astype(bool) & ~entry_events
    return entry_events, clean_exits, direction


def _validate_lengths(entry: int, exit_: int, ema_length: int) -> None:
    _positive_integer(entry, "entry_lookback")
    _positive_integer(exit_, "exit_lookback")
    _positive_integer(ema_length, "ema_length")
    if exit_ >= entry:
        raise ValueError("exit_lookback must be below entry_lookback")


def _validate_squeeze(
    range_lookback: int,
    compression_lookback: int,
    compression_window: int,
    bbwp_max: float,
    clearance_bps: float,
    volume_multiple: float,
    fast_ema: int,
    slow_ema: int,
    minimum_gap_bps: float,
) -> None:
    for value, label in (
        (range_lookback, "range_lookback"),
        (compression_lookback, "compression_lookback"),
        (compression_window, "compression_window"),
        (fast_ema, "fast_ema"),
        (slow_ema, "slow_ema"),
    ):
        _positive_integer(value, label)
    if fast_ema >= slow_ema:
        raise ValueError("fast_ema must be below slow_ema")
    if not 0.0 < bbwp_max < 100.0:
        raise ValueError("bbwp_max must be between 0 and 100")
    _nonnegative(clearance_bps, "clearance_bps")
    _positive(volume_multiple, "volume_multiple")
    _nonnegative(minimum_gap_bps, "minimum_gap_bps")


def _positive_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")


def _positive(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be finite and positive")


def _nonnegative(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{label} must be finite and non-negative")
