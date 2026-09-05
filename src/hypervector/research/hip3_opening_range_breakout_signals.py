"""Causal U.S. cash-session opening-range signals for HIP-3 research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math

import numpy as np
import pandas as pd

from hypervector.strategies.indicators import ema


_NEW_YORK = "America/New_York"
_OPENING_MINUTES = frozenset({570, 585})
_CLOSED_2026 = (date(2026, 6, 19), date(2026, 7, 3))


@dataclass(frozen=True)
class Hip3OpeningRangeBreakoutConfig:
    """Frozen session, trend, clearance, and barrier parameters."""

    clearance_bps: float
    ema_fast: int = 21
    ema_slow: int = 55
    minimum_stop_bps: float = 15.0
    maximum_stop_bps: float = 80.0
    target_r_multiple: float = 2.0
    maximum_hold_bars: int = 24
    closed_session_dates: tuple[date, ...] = _CLOSED_2026

    def __post_init__(self) -> None:
        """Reject malformed frozen parameters before signal construction."""
        lengths = (self.ema_fast, self.ema_slow, self.maximum_hold_bars)
        if any(isinstance(value, bool) or value <= 0 for value in lengths):
            raise ValueError("opening-range bar lengths must be positive integers")
        if self.ema_fast >= self.ema_slow:
            raise ValueError("opening-range fast EMA must be shorter than slow EMA")
        numbers = (
            self.clearance_bps,
            self.minimum_stop_bps,
            self.maximum_stop_bps,
            self.target_r_multiple,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in numbers):
            raise ValueError("opening-range economic parameters must be positive")
        if self.minimum_stop_bps > self.maximum_stop_bps:
            raise ValueError("opening-range minimum stop cannot exceed maximum stop")


def build_hip3_opening_range_breakout_signals(
    bars: pd.DataFrame,
    config: Hip3OpeningRangeBreakoutConfig,
) -> pd.DataFrame:
    """Return first completed-bar breakout entries and causal exits."""
    frame = _validated_bars(bars)
    context = _session_context(frame, config)
    indicators = _indicators(frame, context, config)
    candidates = _entry_candidates(frame, context, indicators, config)
    entries = _first_session_entries(frame, context, candidates, config)
    exits = _exit_signals(frame, context)
    return pd.concat([entries, exits, indicators, context], axis=1)


def _session_context(
    frame: pd.DataFrame, config: Hip3OpeningRangeBreakoutConfig
) -> pd.DataFrame:
    """Attach causal local-session labels and completed opening ranges."""
    local = frame.index.tz_convert(_NEW_YORK)
    context = pd.DataFrame(index=frame.index)
    context["session_date"] = local.date
    context["local_minute"] = local.hour * 60 + local.minute
    weekday = pd.Series(local.weekday, index=frame.index).lt(5)
    closed = context["session_date"].isin(config.closed_session_dates)
    context["session_eligible"] = weekday & ~closed
    opening = context["session_eligible"] & context["local_minute"].isin(
        _OPENING_MINUTES
    )
    grouped = context["session_date"]
    context["opening_range_high"] = (
        frame["high"].where(opening).groupby(grouped).transform("max")
    )
    context["opening_range_low"] = (
        frame["low"].where(opening).groupby(grouped).transform("min")
    )
    context["opening_range_bar_count"] = opening.groupby(grouped).transform("sum")
    return context


def _indicators(
    frame: pd.DataFrame,
    context: pd.DataFrame,
    config: Hip3OpeningRangeBreakoutConfig,
) -> pd.DataFrame:
    """Compute completed-close EMAs independently across causal gap segments."""
    recovery = frame["gap_before_bars"].gt(0)
    segments = recovery.cumsum().astype(int)
    close = frame["close"].astype(float)
    grouped = close.groupby(segments, sort=False)
    output = pd.DataFrame(index=frame.index)
    output["ema_fast"] = grouped.transform(lambda values: ema(values, config.ema_fast))
    output["ema_slow"] = grouped.transform(lambda values: ema(values, config.ema_slow))
    output["segment_history_bars"] = grouped.cumcount() + 1
    output["source_segment_id"] = segments
    output["trend_warmed"] = output["segment_history_bars"].ge(config.ema_slow)
    output["opening_range_ready"] = context["opening_range_bar_count"].eq(2)
    return output


def _entry_candidates(
    frame: pd.DataFrame,
    context: pd.DataFrame,
    indicators: pd.DataFrame,
    config: Hip3OpeningRangeBreakoutConfig,
) -> pd.DataFrame:
    """Build the predeclared long and short completed-bar conjunctions."""
    close = frame["close"].astype(float)
    clearance = config.clearance_bps / 10_000.0
    time_ok = context["local_minute"].between(600, 840, inclusive="both")
    ready = context["session_eligible"] & indicators["opening_range_ready"] & time_ok
    warmed = ready & indicators["trend_warmed"]
    output = pd.DataFrame(index=frame.index)
    output["long"] = (
        warmed
        & close.gt(context["opening_range_high"] * (1.0 + clearance))
        & close.gt(indicators["ema_fast"])
        & indicators["ema_fast"].gt(indicators["ema_slow"])
    )
    output["short"] = (
        warmed
        & close.lt(context["opening_range_low"] * (1.0 - clearance))
        & close.lt(indicators["ema_fast"])
        & indicators["ema_fast"].lt(indicators["ema_slow"])
    )
    output["long_distance_bps"] = 10_000.0 * (close - frame["low"]) / close
    output["short_distance_bps"] = 10_000.0 * (frame["high"] - close) / close
    return output


def _first_session_entries(
    frame: pd.DataFrame,
    context: pd.DataFrame,
    candidates: pd.DataFrame,
    config: Hip3OpeningRangeBreakoutConfig,
) -> pd.DataFrame:
    """Consume the first breakout and attach structural stop/target prices."""
    raw = candidates["long"] | candidates["short"]
    first = raw & raw.groupby(context["session_date"], sort=False).cumsum().eq(1)
    distance = candidates["long_distance_bps"].where(
        candidates["long"], candidates["short_distance_bps"]
    )
    rejected = first & distance.gt(config.maximum_stop_bps)
    long_entry = first & candidates["long"] & ~rejected
    short_entry = first & candidates["short"] & ~rejected
    stop, target = _barriers(frame, long_entry, short_entry, config)
    output = pd.DataFrame(index=frame.index)
    output["long_entry"] = long_entry
    output["short_entry"] = short_entry
    output["entry_direction"] = np.select(
        [long_entry, short_entry], ["long", "short"], default=None
    )
    output["signal_name"] = pd.Series(output["entry_direction"], index=frame.index).map(
        {
            "long": "hip3_us_cash_opening_range_breakout_long@15m",
            "short": "hip3_us_cash_opening_range_breakout_short@15m",
        }
    )
    output["stop_price"] = stop
    output["target_price"] = target
    output["stop_distance_rejected"] = rejected
    output["execution_authority"] = "none"
    return output


def _barriers(
    frame: pd.DataFrame,
    long_entry: pd.Series,
    short_entry: pd.Series,
    config: Hip3OpeningRangeBreakoutConfig,
) -> tuple[pd.Series, pd.Series]:
    """Return signal-time stop and two-R target prices."""
    close = frame["close"].astype(float)
    floor = config.minimum_stop_bps / 10_000.0
    long_stop = pd.concat([frame["low"], close * (1.0 - floor)], axis=1).min(axis=1)
    short_stop = pd.concat([frame["high"], close * (1.0 + floor)], axis=1).max(axis=1)
    stop = long_stop.where(long_entry, short_stop.where(short_entry))
    long_target = close + config.target_r_multiple * (close - long_stop)
    short_target = close - config.target_r_multiple * (short_stop - close)
    target = long_target.where(long_entry, short_target.where(short_entry))
    return stop, target


def _exit_signals(frame: pd.DataFrame, context: pd.DataFrame) -> pd.DataFrame:
    """Return opening-range invalidation and regular-session close exits."""
    recovery = frame["gap_before_bars"].gt(0)
    session_exit = context["session_eligible"] & context["local_minute"].eq(945)
    ready = context["opening_range_bar_count"].eq(2)
    output = pd.DataFrame(index=frame.index)
    output["long_exit"] = (
        recovery
        | session_exit
        | (ready & frame["close"].lt(context["opening_range_low"]))
    )
    output["short_exit"] = (
        recovery
        | session_exit
        | (ready & frame["close"].gt(context["opening_range_high"]))
    )
    return output


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Validate ordered, gap-aware, finite completed OHLC rows."""
    missing = {"open", "high", "low", "close", "gap_before_bars"}.difference(
        bars.columns
    )
    if missing:
        raise ValueError(
            f"opening-range source bars missing columns: {sorted(missing)}"
        )
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("opening-range source bars require timezone-aware timestamps")
    if bars.empty or not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError("opening-range source bars require ordered unique rows")
    output = bars.copy()
    values = output[["open", "high", "low", "close"]].to_numpy(dtype=float)
    gaps = output["gap_before_bars"].to_numpy(dtype=float)
    invalid = not np.isfinite(values).all() or (values <= 0.0).any()
    invalid |= (values[:, 1] < values[:, [0, 2, 3]].max(axis=1)).any()
    invalid |= (values[:, 2] > values[:, [0, 1, 3]].min(axis=1)).any()
    if invalid or not np.isfinite(gaps).all() or (gaps < 0.0).any():
        raise ValueError("opening-range OHLC and gaps are invalid")
    return output
