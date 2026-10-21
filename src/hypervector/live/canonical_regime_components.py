"""Causal observe-only indicator components attached to canonical regime telemetry.

Each column is a completed-bar diagnostic (EMA/SMA gaps and directions,
Heikin-Ashi RSI, choppiness, completed higher-timeframe bias, rolling trend
slope and fit, trend quality). None carries execution authority.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from hypervector.strategies.indicators import choppiness_index, ema, rsi, sma

_BAR_COLUMNS = ("open", "high", "low", "close", "volume")
_ONE_MINUTE = pd.Timedelta(minutes=1)


def build_regime_component_frame(bars: pd.DataFrame) -> pd.DataFrame:
    """Return causal indicator diagnostics without execution authority."""
    frame = _validated_bars(bars)
    gaps = frame.index.to_series().diff().ne(_ONE_MINUTE)
    blocks = [
        _build_contiguous_block(block) for _, block in frame.groupby(gaps.cumsum())
    ]
    return pd.concat(blocks).sort_index()


def _build_contiguous_block(frame: pd.DataFrame) -> pd.DataFrame:
    close = frame["close"]
    ema_21 = ema(close, 21)
    ema_55 = ema(close, 55)
    sma_100 = sma(close, 100)
    sma_200 = sma(close, 200)
    ema_11 = ema(close, 11)
    ema_34 = ema(close, 34)
    harsi = _harsi(frame)
    slope, r_squared = _rolling_trend(close, 20)
    output = pd.DataFrame(index=frame.index)
    output["ema_21_55_gap_bps"] = _gap_bps(ema_21, ema_55)
    output["ema_21_55_direction"] = _direction(ema_21 - ema_55)
    output["sma_100_200_gap_bps"] = _gap_bps(sma_100, sma_200)
    output["sma_100_200_direction"] = _direction(sma_100 - sma_200)
    output["ema_11_34_direction"] = _direction(ema_11 - ema_34)
    output["harsi_direction"] = harsi["direction"]
    output["harsi_smoothed_rsi"] = harsi["smoothed_rsi"]
    output["choppiness_14"] = choppiness_index(frame["high"], frame["low"], close, 14)
    output["mtf_5m_bias"] = _completed_htf_bias(frame, 5)
    output["mtf_15m_bias"] = _completed_htf_bias(frame, 15)
    output["trend_slope_bps"] = slope
    output["trend_r2"] = r_squared
    output["self_aware_tqi"] = _trend_quality_index(frame)
    return output


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(_BAR_COLUMNS).difference(bars.columns))
    if missing:
        raise ValueError(f"regime component bars missing columns: {missing}")
    index = pd.DatetimeIndex(bars.index)
    if index.tz is None or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("regime components require an ordered timezone-aware index")
    frame = bars.loc[:, list(_BAR_COLUMNS)].astype(float).copy()
    values = frame.to_numpy(dtype=np.float64)
    if frame.empty or not np.isfinite(values).all():
        raise ValueError("regime component bars must be finite and non-empty")
    if (values[:, :4] <= 0.0).any() or (values[:, 4] < 0.0).any():
        raise ValueError(
            "regime component prices must be positive and volume nonnegative"
        )
    return frame


def _gap_bps(fast: pd.Series, slow: pd.Series) -> pd.Series:
    return (fast / slow.replace(0.0, np.nan) - 1.0) * 10_000.0


def _direction(values: pd.Series) -> pd.Series:
    return pd.Series(
        np.where(values > 0.0, 1.0, np.where(values < 0.0, -1.0, 0.0)),
        index=values.index,
    )


def _harsi(frame: pd.DataFrame) -> pd.DataFrame:
    close_rsi = rsi(frame["close"], 14) - 50.0
    high_raw = rsi(frame["high"], 14) - 50.0
    low_raw = rsi(frame["low"], 14) - 50.0
    open_rsi = close_rsi.shift(1).fillna(close_rsi)
    high_rsi = pd.concat([high_raw, low_raw], axis=1).max(axis=1)
    low_rsi = pd.concat([high_raw, low_raw], axis=1).min(axis=1)
    ha_close = (open_rsi + high_rsi + low_rsi + close_rsi) / 4.0
    ha_open = _recursive_average(open_rsi, close_rsi, ha_close)
    smoothed = _recursive_smooth(close_rsi)
    return pd.DataFrame(
        {
            "direction": _direction(ha_close - ha_open),
            "smoothed_rsi": smoothed,
        },
        index=frame.index,
    )


def _recursive_average(
    open_rsi: pd.Series,
    close_rsi: pd.Series,
    ha_close: pd.Series,
) -> pd.Series:
    output = np.full(len(open_rsi), np.nan, dtype=np.float64)
    opening = open_rsi.to_numpy(dtype=np.float64)
    closing = close_rsi.to_numpy(dtype=np.float64)
    ha_values = ha_close.to_numpy(dtype=np.float64)
    if len(output):
        output[0] = (opening[0] + closing[0]) / 2.0
    for index in range(1, len(output)):
        output[index] = (output[index - 1] + ha_values[index - 1]) / 2.0
    return pd.Series(output, index=open_rsi.index)


def _recursive_smooth(values: pd.Series) -> pd.Series:
    raw = values.to_numpy(dtype=np.float64)
    output = np.full(len(raw), np.nan, dtype=np.float64)
    if len(raw):
        output[0] = raw[0]
    for index in range(1, len(raw)):
        output[index] = (output[index - 1] + raw[index]) / 2.0
    return pd.Series(output, index=values.index)


def _completed_htf_bias(frame: pd.DataFrame, minutes: int) -> pd.Series:
    rule = f"{minutes}min"
    grouped = frame.resample(rule, label="left", closed="left")
    htf = grouped.agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    htf = htf.loc[grouped["close"].count() == minutes]
    breakout = np.where(
        htf["high"] > htf["high"].shift(1),
        1.0,
        np.where(htf["low"] < htf["low"].shift(1), -1.0, 0.0),
    )
    candle = np.sign(htf["close"] - htf["open"])
    trend = np.sign(htf["close"] - ema(htf["close"], 50))
    bias = pd.Series(breakout + candle + trend, index=htf.index)
    bias.index = bias.index + pd.Timedelta(minutes=minutes - 1)
    return bias.reindex(frame.index, method="ffill")


def _rolling_trend(close: pd.Series, length: int) -> tuple[pd.Series, pd.Series]:
    values = close.to_numpy(dtype=np.float64)
    slopes = np.full(len(values), np.nan, dtype=np.float64)
    r_squared = np.full(len(values), np.nan, dtype=np.float64)
    x = np.arange(length, dtype=np.float64)
    centered_x = x - x.mean()
    denominator = float(np.dot(centered_x, centered_x))
    for end in range(length - 1, len(values)):
        window = values[end - length + 1 : end + 1]
        centered_y = window - window.mean()
        slope = float(np.dot(centered_x, centered_y) / denominator)
        fitted = slope * centered_x
        total = float(np.dot(centered_y, centered_y))
        slopes[end] = slope / window.mean() * 10_000.0
        r_squared[end] = 0.0 if total == 0.0 else float(np.dot(fitted, fitted) / total)
    index = close.index
    return pd.Series(slopes, index=index), pd.Series(r_squared, index=index).clip(
        0.0, 1.0
    )


def _trend_quality_index(frame: pd.DataFrame) -> pd.Series:
    close = frame["close"]
    efficiency = (close - close.shift(20)).abs() / close.diff().abs().rolling(20).sum()
    volume_mean = frame["volume"].rolling(20).mean()
    volume_std = frame["volume"].rolling(20).std(ddof=0).replace(0.0, np.nan)
    volume_z = (frame["volume"] - volume_mean) / volume_std
    volume_state = ((volume_z + 1.0) / 3.0).clip(0.0, 1.0)
    high = frame["high"].rolling(20).max()
    low = frame["low"].rolling(20).min()
    position = (close - low) / (high - low).replace(0.0, np.nan)
    structure = ((position - 0.5).abs() * 2.0).clip(0.0, 1.0)
    momentum = _momentum_persistence(close, 10)
    quality = (
        efficiency.clip(0.0, 1.0) * 0.35
        + volume_state * 0.20
        + structure * 0.25
        + momentum * 0.20
    )
    return quality.clip(0.0, 1.0)


def _momentum_persistence(close: pd.Series, length: int) -> pd.Series:
    values = close.to_numpy(dtype=np.float64)
    changes = np.diff(values, prepend=np.nan)
    output = np.full(len(values), np.nan, dtype=np.float64)
    for index in range(length, len(values)):
        direction = math.copysign(1.0, values[index] - values[index - length])
        aligned = changes[index - length + 1 : index + 1] * direction > 0.0
        output[index] = float(aligned.sum()) / length
    return pd.Series(output, index=close.index)
