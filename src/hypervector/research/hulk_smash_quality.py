"""Causal trend, volatility, and chop evidence for rebuilt Hulk Smash."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.strategies.indicators import supertrend, true_range

_PRICE_COLUMNS = {"open", "high", "low", "close", "volume"}


def build_hulk_quality_frame(
    bars: pd.DataFrame,
    *,
    supertrend_period: int = 10,
    supertrend_multiplier: float = 3.0,
    adx_period: int = 14,
    squeeze_period: int = 20,
) -> pd.DataFrame:
    """Build completed-bar quality evidence without future information."""
    frame = _validated_bars(bars)
    _, trend = supertrend(
        frame["high"],
        frame["low"],
        frame["close"],
        atr_period=supertrend_period,
        multiplier=supertrend_multiplier,
    )
    adx, di_direction = _adx_direction(frame, adx_period)
    squeeze_on, release = _squeeze_state(frame, squeeze_period)
    return pd.DataFrame(
        {
            "supertrend_direction": trend.astype(np.int8),
            "adx": adx,
            "di_direction": di_direction,
            "squeeze_on": squeeze_on,
            "squeeze_release": release,
            "ha_choppy": _heikin_ashi_chop(frame),
        },
        index=frame.index,
    )


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_PRICE_COLUMNS.difference(bars.columns))
    index = pd.DatetimeIndex(bars.index)
    valid_index = index.tz is not None and index.is_monotonic_increasing
    if bars.empty or missing or not valid_index or index.has_duplicates:
        raise ValueError(
            f"invalid Hulk quality bars: missing={missing} index={valid_index}"
        )
    frame = bars.loc[:, sorted(_PRICE_COLUMNS)].astype(float).copy()
    values = frame.to_numpy()
    if (
        not np.isfinite(values).all()
        or (frame[["open", "high", "low", "close"]] <= 0.0).any().any()
    ):
        raise ValueError("Hulk quality OHLCV must be finite with positive prices")
    if frame["volume"].lt(0.0).any():
        raise ValueError("Hulk quality volume must be non-negative")
    return frame


def _adx_direction(frame: pd.DataFrame, period: int) -> tuple[pd.Series, pd.Series]:
    if period < 2:
        raise ValueError("Hulk ADX period must be at least two")
    high, low, close = frame["high"], frame["low"], frame["close"]
    upward, downward = high.diff(), -low.diff()
    plus_dm = upward.where((upward > downward) & (upward > 0.0), 0.0)
    minus_dm = downward.where((downward > upward) & (downward > 0.0), 0.0)
    average_range = _wilder(true_range(high, low, close), period)
    plus_di = 100.0 * _wilder(plus_dm, period) / average_range
    minus_di = 100.0 * _wilder(minus_dm, period) / average_range
    denominator = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / denominator
    adx = _wilder(dx, period)
    valid = plus_di.notna() & minus_di.notna()
    direction = np.where(
        valid & plus_di.gt(minus_di),
        1,
        np.where(valid & minus_di.gt(plus_di), -1, 0),
    )
    return adx, pd.Series(direction.astype(np.int8), index=frame.index)


def _wilder(values: pd.Series, period: int) -> pd.Series:
    return values.ewm(
        alpha=1.0 / period,
        adjust=False,
        min_periods=period,
    ).mean()


def _squeeze_state(frame: pd.DataFrame, period: int) -> tuple[pd.Series, pd.Series]:
    if period < 2:
        raise ValueError("Hulk squeeze period must be at least two")
    close = frame["close"]
    basis = close.rolling(period, min_periods=period).mean()
    deviation = close.rolling(period, min_periods=period).std(ddof=0) * 2.0
    range_mean = (
        true_range(frame["high"], frame["low"], close)
        .rolling(period, min_periods=period)
        .mean()
    )
    squeeze_on = (basis - deviation > basis - 1.5 * range_mean) & (
        basis + deviation < basis + 1.5 * range_mean
    )
    squeeze_on = squeeze_on.fillna(False).astype(bool)
    release = squeeze_on.shift(1, fill_value=False) & ~squeeze_on
    return squeeze_on, release.astype(bool)


def _heikin_ashi_chop(frame: pd.DataFrame) -> pd.Series:
    close = frame[["open", "high", "low", "close"]].mean(axis=1).to_numpy()
    opening = np.empty(len(frame), dtype=float)
    opening[0] = (float(frame["open"].iloc[0]) + float(frame["close"].iloc[0])) / 2.0
    for position in range(1, len(frame)):
        opening[position] = (opening[position - 1] + close[position - 1]) / 2.0
    direction = pd.Series(np.where(close >= opening, 1, -1), index=frame.index)
    flips = direction.ne(direction.shift()).astype(int)
    flips.iloc[0] = 0
    return flips.rolling(5, min_periods=5).sum().ge(3).astype(bool)
