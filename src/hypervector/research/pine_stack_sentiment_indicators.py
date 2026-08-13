"""Indicator primitives for the causal Market Sentiment translation."""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from hypervector.research.pine_stack_adaptive_supertrend import pine_rma

VwapAnchor = Literal["day", "week"]


def pine_rsi(close: pd.Series, length: int) -> pd.Series:
    """Return Wilder RSI with Pine-style edge handling."""
    values = close.to_numpy(dtype=np.float64)
    changes = np.full(len(values), np.nan, dtype=np.float64)
    changes[1:] = np.diff(values)
    gains = np.where(np.isnan(changes), np.nan, np.maximum(changes, 0.0))
    losses = np.where(np.isnan(changes), np.nan, np.maximum(-changes, 0.0))
    average_gain = pine_rma(gains, length=length)
    average_loss = pine_rma(losses, length=length)
    output = np.full(len(values), np.nan, dtype=np.float64)
    both_zero = (average_gain == 0.0) & (average_loss == 0.0)
    output[both_zero] = 50.0
    output[(average_gain > 0.0) & (average_loss == 0.0)] = 100.0
    output[(average_gain == 0.0) & (average_loss > 0.0)] = 0.0
    normal = (average_gain > 0.0) & (average_loss > 0.0)
    ratio = average_gain[normal] / average_loss[normal]
    output[normal] = 100.0 - 100.0 / (1.0 + ratio)
    return pd.Series(output, index=close.index)


def oscillator_sentiment(values: pd.Series, *, bands: tuple[float, float]) -> pd.Series:
    """Map RSI/Stochastic source bands to the Pine 0-100 sentiment scale."""
    lower, upper = bands
    source = values.to_numpy(dtype=np.float64)
    output = np.full(len(source), np.nan, dtype=np.float64)
    high = source > upper
    upper_mid = (source > 50.0) & ~high
    lower_mid = (source > lower) & ~(high | upper_mid)
    low = (source >= 0.0) & ~(high | upper_mid | lower_mid)
    output[high] = _interpolate(source[high], 100.0, upper, 100.0, 75.0)
    output[upper_mid] = _interpolate(source[upper_mid], upper, 50.0, 75.0, 50.0)
    output[lower_mid] = _interpolate(source[lower_mid], 50.0, lower, 50.0, 25.0)
    output[low] = _interpolate(source[low], lower, 0.0, 25.0, 0.0)
    return pd.Series(output, index=values.index)


def stochastic_sentiment(
    source: pd.Series,
    high: pd.Series,
    low: pd.Series,
    *,
    length: int,
    smooth: int,
) -> pd.Series:
    """Return smoothed stochastic mapped to the source sentiment scale."""
    highest = high.rolling(length, min_periods=length).max()
    lowest = low.rolling(length, min_periods=length).min()
    denominator = (highest - lowest).replace(0.0, np.nan)
    stochastic = (source - lowest) / denominator * 100.0
    smoothed = stochastic.rolling(smooth, min_periods=smooth).mean()
    return oscillator_sentiment(smoothed, bands=(20.0, 80.0))


def cci_sentiment(source: pd.Series, *, length: int) -> pd.Series:
    """Return CCI mapped through the source's piecewise sentiment scale."""
    average = source.rolling(length, min_periods=length).mean()
    deviation = source.rolling(length, min_periods=length).apply(
        lambda values: float(np.mean(np.abs(values - values.mean()))), raw=True
    )
    cci = (source - average) / (0.015 * deviation.replace(0.0, np.nan))
    values = cci.to_numpy(dtype=np.float64)
    output = np.full(len(values), np.nan, dtype=np.float64)
    masks = (
        values > 100.0,
        (values >= 0.0) & (values <= 100.0),
        values < -100.0,
        (values < 0.0) & (values >= -100.0),
    )
    output[masks[0]] = np.where(
        values[masks[0]] > 300.0,
        100.0,
        _interpolate(values[masks[0]], 300.0, 100.0, 100.0, 75.0),
    )
    output[masks[1]] = _interpolate(values[masks[1]], 100.0, 0.0, 75.0, 50.0)
    output[masks[2]] = np.where(
        values[masks[2]] < -300.0,
        0.0,
        _interpolate(values[masks[2]], -100.0, -300.0, 25.0, 0.0),
    )
    output[masks[3]] = _interpolate(values[masks[3]], 0.0, -100.0, 50.0, 25.0)
    return pd.Series(output, index=source.index)


def bull_bear_power_sentiment(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    ema_length: int,
) -> pd.Series:
    """Return the source bull-bear-power Bollinger mapping."""
    average = close.ewm(span=ema_length, adjust=False).mean()
    power = high + low - 2.0 * average
    basis = power.rolling(100, min_periods=100).mean()
    deviation = power.rolling(100, min_periods=100).std(ddof=0) * 2.0
    upper, lower = basis + deviation, basis - deviation
    output = pd.Series(np.nan, index=close.index, dtype=float)
    high_outer = power > upper
    high_inner = (power > 0.0) & ~high_outer
    low_outer = power < lower
    low_inner = (power < 0.0) & ~low_outer
    output.loc[high_outer] = np.where(
        power[high_outer] > 1.5 * upper[high_outer],
        100.0,
        _interpolate(
            power[high_outer], 1.5 * upper[high_outer], upper[high_outer], 100.0, 75.0
        ),
    )
    output.loc[high_inner] = _interpolate(
        power[high_inner], upper[high_inner], 0.0, 75.0, 50.0
    )
    output.loc[low_outer] = np.where(
        power[low_outer] < 1.5 * lower[low_outer],
        0.0,
        _interpolate(
            power[low_outer], lower[low_outer], 1.5 * lower[low_outer], 25.0, 0.0
        ),
    )
    output.loc[low_inner] = _interpolate(
        power[low_inner], 0.0, lower[low_inner], 50.0, 25.0
    )
    return output


def state_normalized_sentiment(
    close: pd.Series,
    buy: pd.Series,
    sell: pd.Series,
    *,
    smooth: int,
) -> pd.Series:
    """Translate the source's persistent transition-range normalization."""
    prices = close.to_numpy(dtype=np.float64)
    buys = buy.fillna(False).to_numpy(dtype=np.bool_)
    sells = sell.fillna(False).to_numpy(dtype=np.bool_)
    raw = np.full(len(prices), np.nan, dtype=np.float64)
    state = 0
    maximum = minimum = math.nan
    for position, price in enumerate(prices):
        prior = state
        state = 1 if buys[position] else -1 if sells[position] else state
        if state > prior:
            maximum = price
        elif state < prior:
            minimum = price
        else:
            maximum = price if math.isnan(maximum) else max(price, maximum)
            minimum = price if math.isnan(minimum) else min(price, minimum)
        width = maximum - minimum
        if math.isfinite(width) and width > 0.0:
            raw[position] = (price - minimum) / width * 100.0
    return pd.Series(raw, index=close.index).rolling(smooth, min_periods=smooth).mean()


def anchored_vwap_bands(
    frame: pd.DataFrame,
    *,
    anchor: VwapAnchor,
    standard_deviations: float,
) -> tuple[pd.Series, pd.Series]:
    """Return fixed-anchor volume-weighted upper and lower bands."""
    times = pd.DatetimeIndex(frame["bar_open_at"])
    keys = times.floor("D") if anchor == "day" else times.to_period("W").start_time
    close = frame["close"].to_numpy(dtype=np.float64)
    volume = frame["volume"].to_numpy(dtype=np.float64)
    upper = np.full(len(frame), np.nan, dtype=np.float64)
    lower = np.full(len(frame), np.nan, dtype=np.float64)
    for positions in pd.Series(np.arange(len(frame))).groupby(keys).groups.values():
        selected = np.asarray(list(positions), dtype=np.int64)
        weights = volume[selected]
        weight_sum = np.cumsum(weights)
        valid = weight_sum > 0.0
        mean = np.divide(
            np.cumsum(close[selected] * weights),
            weight_sum,
            out=np.full(len(selected), np.nan),
            where=valid,
        )
        second = np.divide(
            np.cumsum(close[selected] ** 2 * weights),
            weight_sum,
            out=np.full(len(selected), np.nan),
            where=valid,
        )
        deviation = np.sqrt(np.maximum(second - mean**2, 0.0))
        upper[selected] = mean + standard_deviations * deviation
        lower[selected] = mean - standard_deviations * deviation
    return pd.Series(upper, index=frame.index), pd.Series(lower, index=frame.index)


def classic_supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    atr_period: int,
    factor: float,
) -> tuple[pd.Series, pd.Series]:
    """Return a causal classic SuperTrend line and +1/-1 directional state."""
    arrays = (series.to_numpy(dtype=np.float64) for series in (high, low, close))
    highs, lows, closes = arrays
    true_range = highs - lows
    true_range[1:] = np.maximum.reduce(
        (
            true_range[1:],
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:] - closes[:-1]),
        )
    )
    atr = pine_rma(true_range, length=atr_period)
    line = np.full(len(closes), np.nan, dtype=np.float64)
    state = np.zeros(len(closes), dtype=np.int8)
    upper = lower = math.nan
    direction = 1
    for position in range(len(closes)):
        if not math.isfinite(atr[position]):
            continue
        midpoint = (highs[position] + lows[position]) / 2.0
        proposed_upper = midpoint + factor * atr[position]
        proposed_lower = midpoint - factor * atr[position]
        if math.isnan(upper):
            upper, lower = proposed_upper, proposed_lower
        else:
            prior_upper, prior_lower = upper, lower
            prior_close = closes[position - 1]
            upper = (
                min(proposed_upper, prior_upper)
                if prior_close < prior_upper
                else proposed_upper
            )
            lower = (
                max(proposed_lower, prior_lower)
                if prior_close > prior_lower
                else proposed_lower
            )
            direction = (
                1
                if closes[position] > prior_upper
                else -1
                if closes[position] < prior_lower
                else direction
            )
        line[position] = lower if direction == 1 else upper
        state[position] = direction
    return pd.Series(line, index=close.index), pd.Series(state, index=close.index)


def classic_supertrend_line(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    atr_period: int,
    factor: float,
) -> pd.Series:
    """Return only the classic SuperTrend line for sentiment normalization."""
    line, _ = classic_supertrend(high, low, close, atr_period=atr_period, factor=factor)
    return line


def confirmed_market_structure_events(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    pivot_width: int,
) -> tuple[pd.Series, pd.Series]:
    """Return causal first-break events from confirmed strict pivots."""
    highs, lows, closes = (
        series.to_numpy(dtype=np.float64) for series in (high, low, close)
    )
    bullish = np.zeros(len(close), dtype=np.bool_)
    bearish = np.zeros(len(close), dtype=np.bool_)
    pivot_high = pivot_low = math.nan
    high_crossed = low_crossed = False
    for confirmation in range(2 * pivot_width, len(close)):
        center = confirmation - pivot_width
        left = slice(center - pivot_width, center)
        right = slice(center + 1, center + pivot_width + 1)
        if highs[center] >= np.max(highs[left]) and highs[center] > np.max(
            highs[right]
        ):
            pivot_high, high_crossed = highs[center], False
        if lows[center] <= np.min(lows[left]) and lows[center] < np.min(lows[right]):
            pivot_low, low_crossed = lows[center], False
        if (
            math.isfinite(pivot_high)
            and closes[confirmation] > pivot_high
            and not high_crossed
        ):
            bullish[confirmation], high_crossed = True, True
        if (
            math.isfinite(pivot_low)
            and closes[confirmation] < pivot_low
            and not low_crossed
        ):
            bearish[confirmation], low_crossed = True, True
    return pd.Series(bullish, index=close.index), pd.Series(bearish, index=close.index)


def _interpolate(
    value: pd.Series | NDArray[np.float64],
    value_high: float | pd.Series,
    value_low: float | pd.Series,
    range_high: float,
    range_low: float,
) -> pd.Series | NDArray[np.float64]:
    return range_low + (value - value_low) * (range_high - range_low) / (
        value_high - value_low
    )
