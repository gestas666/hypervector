"""Causal bar translations of selected Apex directional entry hypotheses."""

from __future__ import annotations

import numpy as np
import pandas as pd


_REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")
_EMA_FAST = 7
_EMA_SLOW = 26
_ADX_PERIOD = 14
_ENSEMBLE_MEDIUM_WINDOW = 12
_ENSEMBLE_SHORT_WINDOW = 6
_RSI_PERIOD = 8
_MACD_FAST = 14
_MACD_SLOW = 23
_MACD_SIGNAL = 9
_BB_PERIOD = 7
_VOLATILITY_LOOKBACK = 36
_TARGET_VOLATILITY = 0.015
_BASE_THRESHOLD = 0.012


def build_apex_trend_entries(
    bars: pd.DataFrame,
    *,
    adx_threshold: float = 25.0,
) -> pd.DataFrame:
    """Build EMA(7/26) crossover entries confirmed by causal ADX(14)."""
    clean = _validated_bars(bars)
    if not 0.0 <= adx_threshold <= 101.0:
        raise ValueError("ADX threshold must be between zero and 101")
    ema_fast = clean["close"].ewm(span=_EMA_FAST, adjust=False).mean()
    ema_slow = clean["close"].ewm(span=_EMA_SLOW, adjust=False).mean()
    fast_above = ema_fast.gt(ema_slow)
    cross_up = fast_above & ~fast_above.shift(1, fill_value=False)
    cross_down = ~fast_above & fast_above.shift(1, fill_value=False)
    adx = _adx(clean, _ADX_PERIOD)
    ready = pd.Series(
        np.arange(len(clean)) >= 2 * _ADX_PERIOD + 1,
        index=clean.index,
    )
    return pd.DataFrame(
        {
            "long_entry": cross_up & adx.gt(adx_threshold) & ready,
            "short_entry": cross_down & adx.gt(adx_threshold) & ready,
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "adx": adx,
        },
        index=clean.index,
    )


def build_apex_ensemble_entries(
    bars: pd.DataFrame,
    *,
    min_votes: int = 4,
) -> pd.DataFrame:
    """Build fresh Apex ensemble episodes with BB compression kept neutral."""
    clean = _validated_bars(bars)
    if not 1 <= min_votes <= 5:
        raise ValueError("ensemble min_votes must be between one and five")
    indicators = _ensemble_indicators(clean["close"])
    votes = _ensemble_votes(indicators)
    bull = votes["bull_votes"].ge(min_votes)
    bear = votes["bear_votes"].ge(min_votes)
    output = pd.concat((votes, indicators), axis=1)
    output.insert(0, "short_entry", _fresh_episode(bear))
    output.insert(0, "long_entry", _fresh_episode(bull))
    output.attrs["min_votes"] = min_votes
    output.attrs["bb_vote_policy"] = "telemetry_only_direction_neutral"
    return output


def build_apex_breakout_entries(
    bars: pd.DataFrame,
    *,
    lookback: int = 20,
    breakout_threshold_bps: float = 50.0,
    volume_surge_mult: float = 2.0,
) -> pd.DataFrame:
    """Build fresh close breakouts against prior range and prior bar volume."""
    clean = _validated_bars(bars)
    if lookback < 2:
        raise ValueError("breakout lookback must be at least two bars")
    if breakout_threshold_bps < 0.0 or volume_surge_mult <= 0.0:
        raise ValueError("breakout thresholds must be non-negative and positive")
    prior_high = clean["high"].shift(1).rolling(lookback).max()
    prior_low = clean["low"].shift(1).rolling(lookback).min()
    prior_volume = clean["volume"].shift(1).rolling(lookback).mean()
    upside_bps = clean["close"].sub(prior_high).div(prior_high).mul(10_000.0)
    downside_bps = prior_low.sub(clean["close"]).div(prior_low).mul(10_000.0)
    volume_surge = clean["volume"].gt(prior_volume.mul(volume_surge_mult))
    long_condition = upside_bps.gt(breakout_threshold_bps) & volume_surge
    short_condition = downside_bps.gt(breakout_threshold_bps) & volume_surge
    return pd.DataFrame(
        {
            "long_entry": _fresh_episode(long_condition),
            "short_entry": _fresh_episode(short_condition),
            "prior_high": prior_high,
            "prior_low": prior_low,
            "prior_volume_mean": prior_volume,
            "upside_bps": upside_bps,
            "downside_bps": downside_bps,
            "volume_surge": volume_surge,
        },
        index=clean.index,
    )


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(_REQUIRED_COLUMNS).difference(bars.columns))
    if missing:
        raise ValueError(f"Apex signal bars missing columns: {missing}")
    if not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError("Apex signal bars must be strictly ordered and unique")
    clean = bars.loc[:, _REQUIRED_COLUMNS].astype(float)
    if clean.empty or not np.isfinite(clean.to_numpy()).all():
        raise ValueError("Apex signal bars must be non-empty and finite")
    if clean[["open", "high", "low", "close"]].le(0.0).any().any():
        raise ValueError("Apex signal prices must be positive")
    if clean["volume"].lt(0.0).any():
        raise ValueError("Apex signal volume must be non-negative")
    if clean["high"].lt(clean[["open", "low", "close"]].max(axis=1)).any():
        raise ValueError("Apex signal bar high is inconsistent")
    if clean["low"].gt(clean[["open", "high", "close"]].min(axis=1)).any():
        raise ValueError("Apex signal bar low is inconsistent")
    return clean


def _adx(bars: pd.DataFrame, period: int) -> pd.Series:
    previous_close = bars["close"].shift(1)
    true_range = pd.concat(
        (
            bars["high"].sub(bars["low"]),
            bars["high"].sub(previous_close).abs(),
            bars["low"].sub(previous_close).abs(),
        ),
        axis=1,
    ).max(axis=1)
    up_move = bars["high"].diff()
    down_move = bars["low"].shift(1).sub(bars["low"])
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0.0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0.0), 0.0)
    atr = true_range.ewm(alpha=1.0 / period, adjust=False).mean()
    plus_di = plus_dm.ewm(alpha=1.0 / period, adjust=False).mean().div(atr).mul(100.0)
    minus_di = minus_dm.ewm(alpha=1.0 / period, adjust=False).mean().div(atr).mul(100.0)
    denominator = plus_di.add(minus_di).replace(0.0, np.nan)
    dx = plus_di.sub(minus_di).abs().div(denominator).mul(100.0)
    return dx.ewm(alpha=1.0 / period, adjust=False).mean().fillna(0.0)


def _ensemble_indicators(close: pd.Series) -> pd.DataFrame:
    returns = np.log(close.div(close.shift(1)))
    realized_vol = returns.rolling(_VOLATILITY_LOOKBACK - 1).std(ddof=0)
    vol_ratio = realized_vol.div(_TARGET_VOLATILITY)
    threshold = _BASE_THRESHOLD * (0.3 + 0.7 * vol_ratio)
    threshold = threshold.clip(lower=0.005, upper=0.020)
    ema_fast = close.ewm(span=_EMA_FAST, adjust=False).mean()
    ema_slow = close.ewm(span=_EMA_SLOW, adjust=False).mean()
    macd = (
        close.ewm(span=_MACD_FAST, adjust=False)
        .mean()
        .sub(close.ewm(span=_MACD_SLOW, adjust=False).mean())
    )
    return pd.DataFrame(
        {
            "return_medium": close.div(close.shift(_ENSEMBLE_MEDIUM_WINDOW - 1)).sub(
                1.0
            ),
            "return_short": close.div(close.shift(_ENSEMBLE_SHORT_WINDOW - 1)).sub(1.0),
            "dynamic_threshold": threshold,
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "rsi": _rsi(close, _RSI_PERIOD),
            "macd_histogram": macd.sub(
                macd.ewm(span=_MACD_SIGNAL, adjust=False).mean()
            ),
            "bb_compressed": _bb_width_percentile(close).lt(90.0),
        },
        index=close.index,
    )


def _ensemble_votes(indicators: pd.DataFrame) -> pd.DataFrame:
    threshold = indicators["dynamic_threshold"]
    bull = pd.concat(
        (
            indicators["return_medium"].gt(threshold),
            indicators["return_short"].gt(threshold.mul(0.7)),
            indicators["ema_fast"].gt(indicators["ema_slow"]),
            indicators["rsi"].gt(50.0),
            indicators["macd_histogram"].gt(0.0),
        ),
        axis=1,
    )
    bear = pd.concat(
        (
            indicators["return_medium"].lt(-threshold),
            indicators["return_short"].lt(-threshold.mul(0.7)),
            indicators["ema_fast"].lt(indicators["ema_slow"]),
            indicators["rsi"].lt(50.0),
            indicators["macd_histogram"].lt(0.0),
        ),
        axis=1,
    )
    return pd.DataFrame(
        {"bull_votes": bull.sum(axis=1), "bear_votes": bear.sum(axis=1)},
        index=indicators.index,
    )


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    average_gain = delta.clip(lower=0.0).rolling(period).mean()
    average_loss = -delta.clip(upper=0.0).rolling(period).mean()
    relative_strength = average_gain.div(average_loss.replace(0.0, np.nan))
    rsi = 100.0 - 100.0 / (1.0 + relative_strength)
    no_move = average_gain.eq(0.0) & average_loss.eq(0.0)
    return rsi.mask(average_loss.eq(0.0), 100.0).mask(no_move, 50.0).fillna(50.0)


def _bb_width_percentile(close: pd.Series) -> pd.Series:
    mean = close.rolling(_BB_PERIOD).mean()
    width = close.rolling(_BB_PERIOD).std(ddof=0).mul(2.0).div(mean)

    def percentile(values: np.ndarray) -> float:
        return float(np.less(values[:-1], values[-1]).mean() * 100.0)

    return width.rolling(33, min_periods=2).apply(percentile, raw=True).fillna(50.0)


def _fresh_episode(condition: pd.Series) -> pd.Series:
    clean = condition.fillna(False).astype(bool)
    return clean & ~clean.shift(1, fill_value=False)
