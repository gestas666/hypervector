"""Causal RSI-divergence annotations for low-timeframe research."""

from __future__ import annotations

import numpy as np
import pandas as pd

_PIVOT_LEFT = 2
_PIVOT_RIGHT = 2
_BEARISH_ZONE_MINIMUM = 60.0
_BULLISH_ZONE_MAXIMUM = 30.0


def confirmed_regular_rsi_divergence(
    highs: pd.Series,
    lows: pd.Series,
    rsi: pd.Series,
) -> pd.DataFrame:
    """Return causal regular RSI divergences confirmed two bars after a pivot.

    This is the five-bar fractal used by the reviewed Cipher B Pine source.
    A pivot centered at ``t - 2`` is first emitted on completed bar ``t``.
    """
    high, low, oscillator = _validated_arrays(highs, lows, rsi)
    bearish = np.zeros(len(high), dtype=bool)
    bullish = np.zeros(len(high), dtype=bool)
    previous_top: tuple[float, float] | None = None
    previous_bottom: tuple[float, float] | None = None
    for confirmation in range(_PIVOT_LEFT + _PIVOT_RIGHT, len(high)):
        center = confirmation - _PIVOT_RIGHT
        if _is_top(oscillator, center) and oscillator[center] >= _BEARISH_ZONE_MINIMUM:
            current_top = (high[center], oscillator[center])
            if previous_top is not None:
                bearish[confirmation] = (
                    current_top[0] > previous_top[0]
                    and current_top[1] < previous_top[1]
                )
            previous_top = current_top
        if (
            _is_bottom(oscillator, center)
            and oscillator[center] <= _BULLISH_ZONE_MAXIMUM
        ):
            current_bottom = (low[center], oscillator[center])
            if previous_bottom is not None:
                bullish[confirmation] = (
                    current_bottom[0] < previous_bottom[0]
                    and current_bottom[1] > previous_bottom[1]
                )
            previous_bottom = current_bottom
    return pd.DataFrame(
        {
            "rsi_bearish_divergence": bearish,
            "rsi_bullish_divergence": bullish,
        },
        index=highs.index,
    )


def confirmed_three_drive_rsi_divergence(
    highs: pd.Series,
    lows: pd.Series,
    rsi: pd.Series,
) -> pd.DataFrame:
    """Return causal three-drive RSI divergence after the third pivot confirms."""
    high, low, oscillator = _validated_arrays(highs, lows, rsi)
    bearish = np.zeros(len(high), dtype=bool)
    bullish = np.zeros(len(high), dtype=bool)
    bearish_stop = np.full(len(high), np.nan)
    bullish_stop = np.full(len(high), np.nan)
    tops: list[tuple[float, float]] = []
    bottoms: list[tuple[float, float]] = []
    for confirmation in range(_PIVOT_LEFT + _PIVOT_RIGHT, len(high)):
        center = confirmation - _PIVOT_RIGHT
        if _is_top(oscillator, center):
            tops = _qualified_pivots(
                tops,
                (high[center], oscillator[center]),
                oscillator[center] >= _BEARISH_ZONE_MINIMUM,
            )
            if _three_drive(tops, price_rises=True):
                bearish[confirmation] = True
                bearish_stop[confirmation] = high[center]
        if _is_bottom(oscillator, center):
            bottoms = _qualified_pivots(
                bottoms,
                (low[center], oscillator[center]),
                oscillator[center] <= _BULLISH_ZONE_MAXIMUM,
            )
            if _three_drive(bottoms, price_rises=False):
                bullish[confirmation] = True
                bullish_stop[confirmation] = low[center]
    return pd.DataFrame(
        {
            "rsi_three_drive_bearish": bearish,
            "rsi_three_drive_bullish": bullish,
            "bearish_stop_anchor": bearish_stop,
            "bullish_stop_anchor": bullish_stop,
        },
        index=highs.index,
    )


def _qualified_pivots(
    prior: list[tuple[float, float]],
    current: tuple[float, float],
    qualified: bool,
) -> list[tuple[float, float]]:
    """Keep the last three consecutive oscillator-zone pivots."""
    if not qualified:
        return []
    return [*prior[-2:], current]


def _three_drive(pivots: list[tuple[float, float]], *, price_rises: bool) -> bool:
    """Return whether three prices and oscillator values diverge monotonically."""
    if len(pivots) != 3:
        return False
    prices, oscillators = zip(*pivots, strict=True)
    if price_rises:
        return (
            prices[0] < prices[1] < prices[2]
            and oscillators[0] > oscillators[1] > oscillators[2]
        )
    return (
        prices[0] > prices[1] > prices[2]
        and oscillators[0] < oscillators[1] < oscillators[2]
    )


def _validated_arrays(
    highs: pd.Series, lows: pd.Series, rsi: pd.Series
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return aligned finite float arrays or fail with an actionable error."""
    if not (len(highs) == len(lows) == len(rsi)):
        raise ValueError("highs, lows, and RSI must have the same length")
    if not highs.index.equals(lows.index) or not highs.index.equals(rsi.index):
        raise ValueError("highs, lows, and RSI must have the same index")
    arrays = tuple(series.to_numpy(dtype=float) for series in (highs, lows, rsi))
    if any(not np.isfinite(values).all() for values in arrays):
        raise ValueError("highs, lows, and RSI must contain only finite values")
    if np.any(arrays[0] < arrays[1]):
        raise ValueError("each high must be greater than or equal to its low")
    return arrays


def _is_top(values: np.ndarray, center: int) -> bool:
    """Return whether one center is a strict two-left/two-right pivot high."""
    return bool(
        values[center - 2] < values[center]
        and values[center - 1] < values[center]
        and values[center] > values[center + 1]
        and values[center] > values[center + 2]
    )


def _is_bottom(values: np.ndarray, center: int) -> bool:
    """Return whether one center is a strict two-left/two-right pivot low."""
    return bool(
        values[center - 2] > values[center]
        and values[center - 1] > values[center]
        and values[center] < values[center + 1]
        and values[center] < values[center + 2]
    )
