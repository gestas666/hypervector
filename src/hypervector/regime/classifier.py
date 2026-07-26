"""Causal primary regime classification for one completed-bar timeframe."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from hypervector.regime.models import BreakoutDirection, PrimaryRegime
from hypervector.strategies.indicators import (
    bollinger_width,
    choppiness_index,
    ema,
    percentile_rank,
)


@dataclass(frozen=True)
class RegimeClassifierConfig:
    """Validated thresholds for causal market-structure classification."""

    ema_fast: int = 20
    ema_slow: int = 50
    warmup_bars: int = 60
    structure_lookback: int = 180
    trend_strength_percentile: float = 60.0
    range_strength_percentile: float = 30.0
    minimum_trend_gap_bps: float = 5.0
    choppiness_length: int = 14
    choppiness_range_threshold: float = 55.0
    coiling_width_bps: float = 5.0
    breakout_lookback: int = 60
    breakout_clearance_bps: float = 5.0
    breakout_volume_lookback: int = 20
    breakout_volume_multiple: float = 2.0

    def __post_init__(self) -> None:
        _require_integer("ema_fast", self.ema_fast, minimum=1)
        _require_integer("ema_slow", self.ema_slow, minimum=2)
        if not 1 <= self.ema_fast < self.ema_slow:
            raise ValueError("require 1 <= ema_fast < ema_slow")
        _require_integer("warmup_bars", self.warmup_bars, minimum=1)
        if self.warmup_bars < self.ema_slow:
            raise ValueError("warmup_bars must be >= ema_slow")
        _require_integer("structure_lookback", self.structure_lookback, minimum=5)
        _require_percentile("trend_strength_percentile", self.trend_strength_percentile)
        _require_percentile("range_strength_percentile", self.range_strength_percentile)
        if self.range_strength_percentile > self.trend_strength_percentile:
            raise ValueError(
                "range_strength_percentile must be <= trend_strength_percentile"
            )
        _require_non_negative("minimum_trend_gap_bps", self.minimum_trend_gap_bps)
        _require_integer("choppiness_length", self.choppiness_length, minimum=2)
        _require_percentile(
            "choppiness_range_threshold", self.choppiness_range_threshold
        )
        _require_non_negative("coiling_width_bps", self.coiling_width_bps)
        _require_integer("breakout_lookback", self.breakout_lookback, minimum=2)
        _require_non_negative("breakout_clearance_bps", self.breakout_clearance_bps)
        _require_integer(
            "breakout_volume_lookback", self.breakout_volume_lookback, minimum=1
        )
        _require_positive("breakout_volume_multiple", self.breakout_volume_multiple)


def _require_integer(name: str, value: int, *, minimum: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _require_percentile(name: str, value: float) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 100.0:
        raise ValueError(f"{name} must be finite and within [0, 100]")


def _require_non_negative(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")


def _require_positive(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive")


def _validate_bars(df: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"regime bars missing columns: {sorted(missing)}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("regime bars require a DatetimeIndex")
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise ValueError("regime bar index must be unique and increasing")
    values = _numeric_ohlcv(df)
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError("regime bars contain non-finite OHLCV values")
    prices = values[["open", "high", "low", "close"]]
    if (prices <= 0.0).to_numpy().any():
        raise ValueError("regime bar prices must be positive")
    if (values["volume"] < 0.0).any():
        raise ValueError("regime bar volume must be non-negative")
    _validate_ohlc_bounds(values)


def _numeric_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    columns = ["open", "high", "low", "close", "volume"]
    try:
        return df.loc[:, columns].astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError("regime bars require numeric OHLCV values") from exc


def _validate_ohlc_bounds(values: pd.DataFrame) -> None:
    upper = values[["open", "low", "close"]].max(axis=1)
    lower = values[["open", "high", "close"]].min(axis=1)
    invalid = (values["high"] < upper) | (values["low"] > lower)
    if invalid.any():
        timestamp = values.index[invalid][0]
        raise ValueError(f"regime bar OHLC bounds are inconsistent at {timestamp}")


def _breakout_features(
    df: pd.DataFrame,
    cfg: RegimeClassifierConfig,
) -> tuple[pd.Series, pd.Series]:
    close = df["close"].astype(float)
    prior_high = df["high"].shift(1).rolling(cfg.breakout_lookback).max()
    prior_low = df["low"].shift(1).rolling(cfg.breakout_lookback).min()
    prior_volume = (
        df["volume"].astype(float).shift(1).rolling(cfg.breakout_volume_lookback).mean()
    )
    clearance = cfg.breakout_clearance_bps / 10_000.0
    volume_ok = (
        df["volume"].astype(float) >= prior_volume * cfg.breakout_volume_multiple
    )
    upward = (close > prior_high * (1.0 + clearance)) & volume_ok
    downward = (close < prior_low * (1.0 - clearance)) & volume_ok
    return upward.fillna(False), downward.fillna(False)


def _structure_features(
    df: pd.DataFrame,
    cfg: RegimeClassifierConfig,
) -> pd.DataFrame:
    close = df["close"].astype(float)
    gap = (ema(close, cfg.ema_fast) - ema(close, cfg.ema_slow)) / close.replace(
        0.0, np.nan
    )
    strength_bps = gap.abs() * 10_000.0
    width = bollinger_width(close, length=max(5, cfg.choppiness_length))
    width_rank = percentile_rank(width, cfg.structure_lookback)
    return pd.DataFrame(
        {
            "gap": gap,
            "strength_bps": strength_bps,
            "strength_rank": percentile_rank(strength_bps, cfg.structure_lookback),
            "choppiness": choppiness_index(
                df["high"], df["low"], close, cfg.choppiness_length
            ),
            "coiling": (width * 10_000.0 <= cfg.coiling_width_bps)
            | (width_rank <= 20.0),
        },
        index=df.index,
    )


def _assign_primary(
    features: pd.DataFrame,
    breakout_up: pd.Series,
    breakout_down: pd.Series,
    cfg: RegimeClassifierConfig,
) -> pd.Series:
    primary = pd.Series(
        PrimaryRegime.TRANSITION.value, index=features.index, dtype=object
    )
    strong = features["strength_rank"] >= cfg.trend_strength_percentile
    enough_gap = features["strength_bps"] >= cfg.minimum_trend_gap_bps
    not_choppy = features["choppiness"] < cfg.choppiness_range_threshold
    trend = strong | (features["strength_bps"] >= 2.0 * cfg.minimum_trend_gap_bps)
    trend &= enough_gap & not_choppy
    range_state = (
        features["coiling"]
        | (features["strength_rank"] <= cfg.range_strength_percentile)
        | (~enough_gap)
        | (~not_choppy)
    )
    primary = primary.mask(range_state, PrimaryRegime.RANGE.value)
    primary = primary.mask(
        trend & (features["gap"] > 0.0), PrimaryRegime.TREND_UP.value
    )
    primary = primary.mask(
        trend & (features["gap"] < 0.0), PrimaryRegime.TREND_DOWN.value
    )
    primary = primary.mask(breakout_up | breakout_down, PrimaryRegime.BREAKOUT.value)
    if cfg.warmup_bars > 1:
        primary.iloc[: cfg.warmup_bars - 1] = PrimaryRegime.UNKNOWN.value
    return primary


def classify_timeframe(
    df: pd.DataFrame,
    config: RegimeClassifierConfig | None = None,
) -> pd.DataFrame:
    """Classify completed bars without using any future value."""
    _validate_bars(df)
    cfg = config or RegimeClassifierConfig()
    features = _structure_features(df, cfg)
    breakout_up, breakout_down = _breakout_features(df, cfg)
    primary = _assign_primary(features, breakout_up, breakout_down, cfg)
    direction = pd.Series(None, index=df.index, dtype=object)
    direction = direction.mask(breakout_up, BreakoutDirection.UPWARD.value)
    direction = direction.mask(breakout_down, BreakoutDirection.DOWNWARD.value)
    direction = direction.where(primary == PrimaryRegime.BREAKOUT.value, None)
    strength_percentile = features["strength_rank"].clip(0.0, 100.0).fillna(0.0)
    strength_score = strength_percentile / 100.0
    reason = primary.map(
        {
            PrimaryRegime.TREND_UP.value: "positive_trend_structure",
            PrimaryRegime.TREND_DOWN.value: "negative_trend_structure",
            PrimaryRegime.BREAKOUT.value: "confirmed_prior_range_break",
            PrimaryRegime.RANGE.value: "range_or_compression_structure",
            PrimaryRegime.TRANSITION.value: "mixed_structure",
            PrimaryRegime.UNKNOWN.value: "warmup_incomplete",
        }
    )
    return pd.DataFrame(
        {
            "primary_regime": primary,
            "breakout_direction": direction,
            "confidence": strength_score,
            "regime_strength_score": strength_score,
            "regime_strength_percentile": strength_percentile,
            "regime_score_source": "ema_gap_strength_percentile_rank",
            "reason": reason,
            "coiling": features["coiling"].fillna(False).astype(bool),
        },
        index=df.index,
    )
