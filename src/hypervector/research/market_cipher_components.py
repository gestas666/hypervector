"""Causal decision-time components for recovered Market Cipher strategies."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from numpy.typing import NDArray


_PRICE_COLUMNS = ("open", "high", "low", "close", "volume")


def build_market_cipher_components(
    bars: pd.DataFrame,
    *,
    wt1: NDArray[np.float64],
    wt2: NDArray[np.float64],
    ema_11: NDArray[np.float64],
    ema_15: NDArray[np.float64],
    ema_34: NDArray[np.float64],
    rsi_14: NDArray[np.float64],
    stoch_k: NDArray[np.float64],
    stoch_d: NDArray[np.float64],
    krown_rsi: NDArray[np.float64],
    krown_rsi_ema: NDArray[np.float64],
    krown_direction: NDArray[np.float64],
    bar_minutes: int,
) -> pd.DataFrame:
    """Combine aligned Pine-style arrays into one causal component frame."""
    frame = _validated_bars(bars)
    arrays = _validated_arrays(
        len(frame),
        wt1,
        wt2,
        ema_11,
        ema_15,
        ema_34,
        rsi_14,
        stoch_k,
        stoch_d,
        krown_rsi,
        krown_rsi_ema,
        krown_direction,
    )
    opening, high, low, close, volume = (
        frame[column].to_numpy(dtype=np.float64) for column in _PRICE_COLUMNS
    )
    wave_cross = _wave_cross(arrays[0], arrays[1])
    flow_value, flow_direction = _money_flow(opening, high, low, close)
    price_vwap, vwap_alignment = _price_vwap(high, low, close, volume, bar_minutes)
    volume_ratio = _volume_ratio(volume)
    ema_trend, ema_slope = _ema_context(arrays[2], arrays[4])
    return pd.DataFrame(
        {
            "wt1": arrays[0],
            "wt2": arrays[1],
            "wave_cross": wave_cross,
            "money_flow_value": flow_value,
            "money_flow_direction": flow_direction,
            "price_vwap": price_vwap,
            "price_vwap_alignment": vwap_alignment,
            "volume_ratio": volume_ratio,
            "volume_above_average": volume_ratio > 1.0,
            "volume_surge": volume_ratio >= 1.5,
            "ema_11": arrays[2],
            "ema_15": arrays[3],
            "ema_34": arrays[4],
            "ema_trend": ema_trend,
            "ema_slope_bps": ema_slope,
            "rsi_14": arrays[5],
            "stoch_k": arrays[6],
            "stoch_d": arrays[7],
            "krown_rsi": arrays[8],
            "krown_rsi_ema": arrays[9],
            "krown_direction": arrays[10].astype(np.int8),
            "krown_zone_context": _krown_zone(arrays[8]),
        },
        index=frame.index,
    )


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize the OHLCV component input."""
    missing = sorted(set(_PRICE_COLUMNS).difference(bars.columns))
    if missing:
        raise ValueError(f"Market Cipher component bars missing columns: {missing}")
    index = pd.DatetimeIndex(bars.index)
    if index.tz is None or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("Market Cipher components require an ordered aware index")
    frame = bars.loc[:, list(_PRICE_COLUMNS)].copy()
    values = frame.to_numpy(dtype=np.float64)
    if frame.empty or not np.isfinite(values).all():
        raise ValueError("Market Cipher component bars must be finite and non-empty")
    if (values[:, :4] <= 0.0).any() or (values[:, 4] < 0.0).any():
        raise ValueError(
            "Market Cipher prices must be positive and volume non-negative"
        )
    return frame


def _validated_arrays(
    rows: int, *values: NDArray[np.float64]
) -> tuple[NDArray[np.float64], ...]:
    """Return aligned one-dimensional floating indicator arrays."""
    arrays = tuple(np.asarray(value, dtype=np.float64) for value in values)
    if any(value.ndim != 1 or len(value) != rows for value in arrays):
        raise ValueError(
            "Market Cipher indicator arrays must be one-dimensional and aligned"
        )
    if any(np.isinf(value).any() for value in arrays):
        raise ValueError("Market Cipher indicator arrays cannot contain infinity")
    return arrays


def _wave_cross(wt1: NDArray[np.float64], wt2: NDArray[np.float64]) -> NDArray[np.int8]:
    """Return +1/-1 only on completed WaveTrend cross bars."""
    output = np.zeros(len(wt1), dtype=np.int8)
    valid = np.isfinite(wt1) & np.isfinite(wt2)
    up = valid[:-1] & valid[1:] & (wt1[:-1] <= wt2[:-1]) & (wt1[1:] > wt2[1:])
    down = valid[:-1] & valid[1:] & (wt1[:-1] >= wt2[:-1]) & (wt1[1:] < wt2[1:])
    output[1:] = np.where(up, 1, np.where(down, -1, 0)).astype(np.int8)
    return output


def _money_flow(
    opening: NDArray[np.float64],
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.int8]]:
    """Return Cipher B RSI+MFI area value and sign."""
    spread = high - low
    raw = np.full(len(close), np.nan, dtype=np.float64)
    valid = spread != 0.0
    raw[valid] = (close[valid] - opening[valid]) / spread[valid] * 150.0
    value = pd.Series(raw).rolling(60, min_periods=60).mean().to_numpy() - 2.5
    direction = np.where(value > 0.0, 1, np.where(value < 0.0, -1, 0))
    return value, direction.astype(np.int8)


def _price_vwap(
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
    volume: NDArray[np.float64],
    bar_minutes: int,
) -> tuple[NDArray[np.float64], NDArray[np.int8]]:
    """Return rolling 24-hour price VWAP and close-price alignment."""
    if bar_minutes < 1 or 1_440 % bar_minutes != 0:
        raise ValueError("Market Cipher bar minutes must divide one day")
    period = 1_440 // bar_minutes
    typical = (high + low + close) / 3.0
    numerator = pd.Series(typical * volume).rolling(period).sum().to_numpy()
    denominator = pd.Series(volume).rolling(period).sum().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        price_vwap = np.where(denominator > 0.0, numerator / denominator, np.nan)
    direction = np.where(close > price_vwap, 1, np.where(close < price_vwap, -1, 0))
    return price_vwap, direction.astype(np.int8)


def _volume_ratio(volume: NDArray[np.float64]) -> NDArray[np.float64]:
    """Return current volume divided by the preceding 20-bar mean."""
    preceding = pd.Series(volume).shift(1).rolling(20).mean().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(preceding > 0.0, volume / preceding, np.nan)


def _ema_context(
    ema_11: NDArray[np.float64], ema_34: NDArray[np.float64]
) -> tuple[NDArray[np.int8], NDArray[np.float64]]:
    """Return EMA 11/34 direction and one-bar fast-EMA slope in bps."""
    valid = np.isfinite(ema_11) & np.isfinite(ema_34)
    trend = np.where(
        valid & (ema_11 > ema_34),
        1,
        np.where(valid & (ema_11 < ema_34), -1, 0),
    ).astype(np.int8)
    slope = np.full(len(ema_11), np.nan, dtype=np.float64)
    prior = ema_11[:-1]
    slope[1:] = np.where(
        np.isfinite(prior) & np.isfinite(ema_11[1:]) & (prior != 0.0),
        (ema_11[1:] / prior - 1.0) * 10_000.0,
        math.nan,
    )
    return trend, slope


def _krown_zone(rsi_values: NDArray[np.float64]) -> NDArray[np.int8]:
    """Encode Pine's visual bull/bear RSI zones as optional context."""
    return np.where(
        rsi_values >= 65.0,
        1,
        np.where(rsi_values <= 45.0, -1, 0),
    ).astype(np.int8)
