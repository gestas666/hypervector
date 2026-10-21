"""Causal decision construction for the liquidity-sweep long challenger."""

from __future__ import annotations

import math
from functools import partial
from pathlib import Path

import pandas as pd

from hypervector.research.shared_strategy_signals import (
    build_strategy_pair_signals_from_specs,
)
from hypervector.strategies.indicators import ema
from hypervector.strategies.registry import StrategySpec

LIQUIDITY_SWEEP_LOOKBACK = 20
LIQUIDITY_SWEEP_CLEARANCE_BPS = 2.0
LIQUIDITY_SWEEP_VOLUME_MULTIPLE = 1.2
LIQUIDITY_SWEEP_EMA_LENGTH = 55


def liquidity_sweep_signals(
    df: pd.DataFrame,
    *,
    direction: str,
    lookback: int = LIQUIDITY_SWEEP_LOOKBACK,
    clearance_bps: float = LIQUIDITY_SWEEP_CLEARANCE_BPS,
    volume_multiple: float = LIQUIDITY_SWEEP_VOLUME_MULTIPLE,
    ema_length: int = LIQUIDITY_SWEEP_EMA_LENGTH,
) -> tuple[pd.Series, pd.Series, str]:
    """Trade wick sweeps that reclaim a prior range boundary with trend bias."""
    for value, label in ((lookback, "lookback"), (ema_length, "ema_length")):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{label} must be a positive integer")
    if not math.isfinite(clearance_bps) or clearance_bps < 0.0:
        raise ValueError("clearance_bps must be finite and non-negative")
    if not math.isfinite(volume_multiple) or volume_multiple <= 0.0:
        raise ValueError("volume_multiple must be finite and positive")
    missing = sorted({"high", "low", "close", "volume"}.difference(df.columns))
    if missing:
        raise ValueError(f"strategy bars missing required columns: {missing}")
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    volume = df["volume"].astype(float)
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
        raw_entry, exits = bull_sweep & (close >= trend), bear_sweep
    else:
        raw_entry, exits = bear_sweep & (close <= trend), bull_sweep
    entry_events = raw_entry.fillna(False).astype(bool)
    entry_events &= ~entry_events.shift(1, fill_value=False)
    clean_exits = exits.fillna(False).astype(bool) & ~entry_events
    return entry_events, clean_exits, direction


_LIQUIDITY_SWEEP_LONG = StrategySpec(
    name="liquidity_sweep_long",
    role="uptrend",
    param_grid={},
    build_signals=partial(liquidity_sweep_signals, direction="long"),
    description="Wick sweep and reclaim long",
)


def load_minute_bars(path: Path) -> pd.DataFrame:
    """Load unique chronological UTC one-minute OHLCV evidence."""
    if not path.is_file():
        raise FileNotFoundError(f"long replay bars are missing: {path}")
    frame = pd.read_parquet(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"long replay bars are missing columns: {missing}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    result = frame.set_index("timestamp").sort_index()
    if result.index.has_duplicates:
        raise ValueError("long replay bars contain duplicate timestamps")
    cadence = result.index.to_series().diff().iloc[1:]
    if len(result) < 2 or cadence.ne(pd.Timedelta(minutes=1)).any():
        raise ValueError("long replay bars require uninterrupted one-minute cadence")
    return result


def completed_hourly_bars(minute_bars: pd.DataFrame) -> pd.DataFrame:
    """Aggregate only complete causal 60-row hourly bars."""
    grouped = minute_bars.resample("1h", label="left", closed="left")
    result = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    return result.loc[grouped.size().eq(60)].dropna()


def maker_decisions_from_hourly_signals(signals: pd.DataFrame) -> pd.DataFrame:
    """Project completed hourly entry pulses onto 10:59-style close timestamps."""
    required = {"long_entry", "long_exit"}
    missing = sorted(required.difference(signals.columns))
    if missing:
        raise ValueError(f"long hourly signals are missing columns: {missing}")
    if not isinstance(signals.index, pd.DatetimeIndex) or signals.index.tz is None:
        raise ValueError("long hourly signals require a timezone-aware DatetimeIndex")
    available_index = signals.index + pd.Timedelta(minutes=59)
    direction = pd.Series(
        ["long" if bool(value) else None for value in signals["long_entry"]],
        index=available_index,
        dtype=object,
    )
    result = pd.DataFrame(
        {
            "entry_direction": direction,
            "structural_direction": direction,
        },
        index=available_index,
    )
    return result


def build_liquidity_sweep_long_decisions(minute_bars: pd.DataFrame) -> pd.DataFrame:
    """Build default-source liquidity-sweep long pulses without a short arm."""
    hourly = completed_hourly_bars(minute_bars)
    signals = build_strategy_pair_signals_from_specs(
        hourly,
        long_spec=_LIQUIDITY_SWEEP_LONG,
        short_spec=None,
    )
    return maker_decisions_from_hourly_signals(signals)
