"""Causal decision construction for the liquidity-sweep long challenger."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hypervector.research.shared_strategy_signals import (
    build_registered_strategy_pair_signals,
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
    signals = build_registered_strategy_pair_signals(
        hourly,
        long_strategy_name="liquidity_sweep_long",
        short_strategy_name=None,
    )
    return maker_decisions_from_hourly_signals(signals)
