"""Causal 15-minute Krown trend-resumption research signals."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from hypervector.strategies.indicators import ema, rsi


@dataclass(frozen=True)
class Hip3KrownTrendResumptionConfig:
    """Frozen Pine-derived indicator lengths and research risk limits."""

    rsi_length: int = 14
    rsi_ema_length: int = 12
    price_ema_fast: int = 21
    price_ema_slow: int = 55
    rsi_midline: float = 50.0
    protective_stop_bps: float = 80.0
    maximum_hold_bars: int = 96

    def __post_init__(self) -> None:
        """Reject malformed or economically ambiguous frozen parameters."""
        integers = (
            self.rsi_length,
            self.rsi_ema_length,
            self.price_ema_fast,
            self.price_ema_slow,
            self.maximum_hold_bars,
        )
        if any(isinstance(value, bool) or value <= 0 for value in integers):
            raise ValueError("Krown bar lengths must be positive integers")
        if self.price_ema_fast >= self.price_ema_slow:
            raise ValueError("Krown fast EMA must be shorter than slow EMA")
        if not 0.0 < self.rsi_midline < 100.0:
            raise ValueError("Krown RSI midline must be within (0, 100)")
        if not math.isfinite(self.protective_stop_bps) or self.protective_stop_bps <= 0:
            raise ValueError("Krown protective stop must be positive and finite")


def build_hip3_krown_trend_resumption_signals(
    bars: pd.DataFrame,
    config: Hip3KrownTrendResumptionConfig = Hip3KrownTrendResumptionConfig(),
) -> pd.DataFrame:
    """Return fresh bidirectional entries and completed-bar exits."""
    frame = _validated_bars(bars)
    recovery = frame["gap_before_bars"].gt(0)
    segments = recovery.cumsum().astype(int)
    close = frame["close"].astype(float)
    indicators = _indicators(close, segments, config)
    signals = _signals(indicators, segments, recovery, config)
    return pd.concat([signals, indicators], axis=1)


def _indicators(
    close: pd.Series,
    segments: pd.Series,
    config: Hip3KrownTrendResumptionConfig,
) -> pd.DataFrame:
    """Compute every indicator independently within each continuous segment."""
    grouped = close.groupby(segments, sort=False)
    rsi_value = grouped.transform(lambda values: rsi(values, config.rsi_length))
    rsi_ema = rsi_value.groupby(segments, sort=False).transform(
        lambda values: ema(values, config.rsi_ema_length)
    )
    output = pd.DataFrame(index=close.index)
    output["close"] = close
    output["ema_fast"] = grouped.transform(
        lambda values: ema(values, config.price_ema_fast)
    )
    output["ema_slow"] = grouped.transform(
        lambda values: ema(values, config.price_ema_slow)
    )
    output["rsi"] = rsi_value
    output["rsi_ema"] = rsi_ema
    output["rsi_ema_slope"] = rsi_ema.groupby(segments, sort=False).diff()
    output["source_segment_id"] = segments
    output["segment_history_bars"] = grouped.cumcount() + 1
    return output


def _signals(
    values: pd.DataFrame,
    segments: pd.Series,
    recovery: pd.Series,
    config: Hip3KrownTrendResumptionConfig,
) -> pd.DataFrame:
    """Translate the frozen completed-indicator conjunction into actions."""
    slope = values["rsi_ema_slope"]
    prior_slope = slope.groupby(segments, sort=False).shift(1)
    warmed = values["segment_history_bars"].ge(config.price_ema_slow)
    long_entry = (
        warmed & _long_alignment(values, config) & slope.gt(0) & prior_slope.le(0)
    )
    short_entry = (
        warmed & _short_alignment(values, config) & slope.lt(0) & prior_slope.ge(0)
    )
    long_exit = recovery | slope.le(0) | values["ema_fast"].le(values["ema_slow"])
    short_exit = recovery | slope.ge(0) | values["ema_fast"].ge(values["ema_slow"])
    output = pd.DataFrame(index=values.index)
    output["long_entry"] = long_entry.fillna(False)
    output["short_entry"] = short_entry.fillna(False)
    output["entry_direction"] = _entry_direction(output)
    output["long_exit"] = long_exit.fillna(False)
    output["short_exit"] = short_exit.fillna(False)
    output["signal_name"] = output["entry_direction"].map(
        {
            "long": "hip3_krown_trend_resumption_long@15m",
            "short": "hip3_krown_trend_resumption_short@15m",
        }
    )
    output["target_price"] = np.nan
    output["stop_price"] = np.nan
    output["execution_authority"] = "none"
    return output


def _long_alignment(
    values: pd.DataFrame, config: Hip3KrownTrendResumptionConfig
) -> pd.Series:
    """Return the predeclared completed long context."""
    return (
        values["close"].gt(values["ema_fast"])
        & values["ema_fast"].gt(values["ema_slow"])
        & values["rsi"].gt(values["rsi_ema"])
        & values["rsi_ema"].ge(config.rsi_midline)
    )


def _short_alignment(
    values: pd.DataFrame, config: Hip3KrownTrendResumptionConfig
) -> pd.Series:
    """Return the predeclared completed short context."""
    return (
        values["close"].lt(values["ema_fast"])
        & values["ema_fast"].lt(values["ema_slow"])
        & values["rsi"].lt(values["rsi_ema"])
        & values["rsi_ema"].le(config.rsi_midline)
    )


def _entry_direction(signals: pd.DataFrame) -> pd.Series:
    """Return one explicit direction only on a fresh entry row."""
    direction = pd.Series(None, index=signals.index, dtype=object)
    direction.loc[signals["long_entry"]] = "long"
    direction.loc[signals["short_entry"]] = "short"
    return direction


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Validate exact ordered source rows without filling unknown gaps."""
    missing = {"close", "gap_before_bars"}.difference(bars.columns)
    if missing:
        raise ValueError(f"Krown source bars missing columns: {sorted(missing)}")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("Krown source bars require timezone-aware timestamps")
    if bars.empty or not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError("Krown source bars require ordered unique rows")
    close = bars["close"].to_numpy(dtype=float)
    gaps = bars["gap_before_bars"].to_numpy(dtype=float)
    if not np.isfinite(close).all() or (close <= 0.0).any():
        raise ValueError("Krown source closes must be positive and finite")
    if (
        not np.isfinite(gaps).all()
        or (gaps < 0.0).any()
        or not np.equal(gaps, np.floor(gaps)).all()
    ):
        raise ValueError("Krown source gaps must be non-negative integers")
    return bars.copy()
