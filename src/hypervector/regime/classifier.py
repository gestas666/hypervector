"""Causal primary regime classification for one completed-bar timeframe."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from hypervector.regime.models import BreakoutDirection, PrimaryRegime
from hypervector.strategies.indicators import (
    bbwp,
    bollinger_width,
    choppiness_index,
    ema,
    percentile_rank,
    rsi,
)


@dataclass(frozen=True)
class RegimeClassifierConfig:
    """Validated thresholds for causal market-structure classification."""

    ema_fast: int = 21
    ema_slow: int = 55
    warmup_bars: int = 60
    structure_lookback: int = 240
    trend_strength_percentile: float = 60.0
    range_strength_percentile: float = 30.0
    minimum_trend_gap_bps: float = 5.0
    range_filter: Literal["bbwp", "choppiness"] = "bbwp"
    choppiness_length: int = 14
    choppiness_range_threshold: float = 85.0
    bbwp_length: int = 20
    bbwp_lookback: int = 240
    bbwp_compression_threshold: float = 25.0
    rsi_length: int = 14
    rsi_signal_length: int = 7
    coiling_width_bps: float = 5.0
    breakout_lookback: int = 60
    breakout_clearance_bps: float = 8.0
    breakout_volume_lookback: int = 20
    breakout_volume_multiple: float = 2.5

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
            raise ValueError("range_strength_percentile must be <= trend_strength_percentile")
        _require_non_negative("minimum_trend_gap_bps", self.minimum_trend_gap_bps)
        if self.range_filter not in {"bbwp", "choppiness"}:
            raise ValueError("range_filter must be bbwp|choppiness")
        _require_integer("choppiness_length", self.choppiness_length, minimum=2)
        _require_percentile("choppiness_range_threshold", self.choppiness_range_threshold)
        _require_integer("bbwp_length", self.bbwp_length, minimum=2)
        _require_integer("bbwp_lookback", self.bbwp_lookback, minimum=5)
        _require_percentile("bbwp_compression_threshold", self.bbwp_compression_threshold)
        _require_integer("rsi_length", self.rsi_length, minimum=2)
        _require_integer("rsi_signal_length", self.rsi_signal_length, minimum=2)
        _require_non_negative("coiling_width_bps", self.coiling_width_bps)
        _require_integer("breakout_lookback", self.breakout_lookback, minimum=2)
        _require_non_negative("breakout_clearance_bps", self.breakout_clearance_bps)
        _require_integer("breakout_volume_lookback", self.breakout_volume_lookback, minimum=1)
        _require_positive("breakout_volume_multiple", self.breakout_volume_multiple)


def hyperliquid_native_regime_config() -> RegimeClassifierConfig:
    """Stability-aware thresholds measured on Hyperliquid-native 1m candles.

    Compared with the defaults it accepts weaker trends (50th/40th strength
    percentiles, 1 bps EMA gap), a tighter 3 bps coil and a 90-bar breakout
    range; ``regime export`` uses it for its per-bar snapshots.
    """
    return RegimeClassifierConfig(
        ema_fast=21,
        ema_slow=55,
        warmup_bars=60,
        structure_lookback=240,
        trend_strength_percentile=50.0,
        range_strength_percentile=40.0,
        minimum_trend_gap_bps=1.0,
        range_filter="bbwp",
        bbwp_length=20,
        bbwp_lookback=240,
        bbwp_compression_threshold=25.0,
        rsi_length=14,
        rsi_signal_length=7,
        coiling_width_bps=3.0,
        breakout_lookback=90,
        breakout_clearance_bps=8.0,
        breakout_volume_multiple=2.5,
    )


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


def validate_regime_bars(df: pd.DataFrame) -> None:
    """Reject malformed OHLCV input independently of indicator construction."""
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
) -> pd.DataFrame:
    close = df["close"].astype(float)
    prior_high = df["high"].shift(1).rolling(cfg.breakout_lookback).max()
    prior_low = df["low"].shift(1).rolling(cfg.breakout_lookback).min()
    prior_volume = df["volume"].astype(float).shift(1).rolling(cfg.breakout_volume_lookback).mean()
    clearance = cfg.breakout_clearance_bps / 10_000.0
    volume = df["volume"].astype(float)
    volume_ratio = volume / prior_volume.replace(0.0, np.nan)
    volume_ok = volume_ratio >= cfg.breakout_volume_multiple
    upward = (close > prior_high * (1.0 + clearance)) & volume_ok
    downward = (close < prior_low * (1.0 - clearance)) & volume_ok
    return pd.DataFrame(
        {
            "upward": upward.fillna(False),
            "downward": downward.fillna(False),
            "volume_ratio": volume_ratio,
            "prior_high": prior_high,
            "prior_low": prior_low,
        },
        index=df.index,
    )


def _momentum_features(close: pd.Series, cfg: RegimeClassifierConfig) -> pd.DataFrame:
    values = rsi(close, cfg.rsi_length)
    signal = ema(values, cfg.rsi_signal_length)
    crossed_up = (values > signal) & (values.shift(1) <= signal.shift(1))
    crossed_down = (values < signal) & (values.shift(1) >= signal.shift(1))
    direction = pd.Series(None, index=close.index, dtype=object)
    direction = direction.mask(crossed_up, BreakoutDirection.UPWARD.value)
    direction = direction.mask(crossed_down, BreakoutDirection.DOWNWARD.value)
    return pd.DataFrame(
        {"rsi": values, "rsi_ema": signal, "rsi_cross_direction": direction},
        index=close.index,
    )


def _structure_features(
    df: pd.DataFrame,
    cfg: RegimeClassifierConfig,
) -> pd.DataFrame:
    close = df["close"].astype(float)
    gap = (ema(close, cfg.ema_fast) - ema(close, cfg.ema_slow)) / close.replace(0.0, np.nan)
    strength_bps = gap.abs() * 10_000.0
    width = bollinger_width(close, length=cfg.bbwp_length)
    width_rank = percentile_rank(width, cfg.structure_lookback)
    bbwp_percentile, _ = bbwp(
        close,
        bb_length=cfg.bbwp_length,
        lookback=cfg.bbwp_lookback,
    )
    compression = bbwp_percentile < cfg.bbwp_compression_threshold
    choppiness = choppiness_index(df["high"], df["low"], close, cfg.choppiness_length)
    range_filter_active = (
        compression if cfg.range_filter == "bbwp" else choppiness >= cfg.choppiness_range_threshold
    )
    return pd.DataFrame(
        {
            "gap": gap,
            "ema_gap_bps_signed": gap * 10_000.0,
            "strength_bps": strength_bps,
            "strength_rank": percentile_rank(strength_bps, cfg.structure_lookback),
            "bbwp_percentile": bbwp_percentile,
            "compression": compression.fillna(False),
            "choppiness": choppiness,
            "range_filter_active": range_filter_active.fillna(False),
            "coiling": (width * 10_000.0 <= cfg.coiling_width_bps)
            | (width_rank <= 20.0)
            | compression.fillna(False),
        },
        index=df.index,
    )


def _assign_primary(
    features: pd.DataFrame,
    breakout: pd.DataFrame,
    cfg: RegimeClassifierConfig,
) -> pd.Series:
    primary = pd.Series(PrimaryRegime.TRANSITION.value, index=features.index, dtype=object)
    strong = features["strength_rank"] >= cfg.trend_strength_percentile
    enough_gap = features["strength_bps"] >= cfg.minimum_trend_gap_bps
    trend = strong | (features["strength_bps"] >= 2.0 * cfg.minimum_trend_gap_bps)
    trend &= enough_gap
    if cfg.range_filter == "choppiness":
        trend &= ~features["range_filter_active"]
    range_state = (
        features["coiling"]
        | (features["strength_rank"] <= cfg.range_strength_percentile)
        | (~enough_gap)
        | features["range_filter_active"]
    )
    primary = primary.mask(range_state, PrimaryRegime.RANGE.value)
    primary = primary.mask(trend & (features["gap"] > 0.0), PrimaryRegime.TREND_UP.value)
    primary = primary.mask(trend & (features["gap"] < 0.0), PrimaryRegime.TREND_DOWN.value)
    primary = primary.mask(
        breakout["upward"] | breakout["downward"],
        PrimaryRegime.BREAKOUT.value,
    )
    if cfg.warmup_bars > 1:
        primary.iloc[: cfg.warmup_bars - 1] = PrimaryRegime.UNKNOWN.value
    return primary


def _tactical_direction(
    breakout_direction: pd.Series,
    features: pd.DataFrame,
    momentum: pd.DataFrame,
    cfg: RegimeClassifierConfig,
) -> pd.Series:
    compression_ready = features["compression"].shift(1).fillna(False)
    gap = features["ema_gap_bps_signed"]
    rsi_cross = momentum["rsi_cross_direction"]
    upward = (
        breakout_direction.eq(BreakoutDirection.UPWARD.value)
        & compression_ready
        & gap.ge(cfg.minimum_trend_gap_bps)
        & rsi_cross.eq(BreakoutDirection.UPWARD.value)
    )
    downward = (
        breakout_direction.eq(BreakoutDirection.DOWNWARD.value)
        & compression_ready
        & gap.le(-cfg.minimum_trend_gap_bps)
        & rsi_cross.eq(BreakoutDirection.DOWNWARD.value)
    )
    tactical = pd.Series(None, index=features.index, dtype=object)
    tactical = tactical.mask(upward, BreakoutDirection.UPWARD.value)
    return tactical.mask(downward, BreakoutDirection.DOWNWARD.value)


def _classification_frame(
    primary: pd.Series,
    direction: pd.Series,
    features: pd.DataFrame,
    momentum: pd.DataFrame,
    breakout: pd.DataFrame,
    tactical: pd.Series,
    reason: pd.Series,
    config: RegimeClassifierConfig,
) -> pd.DataFrame:
    strength_percentile = features["strength_rank"].clip(0.0, 100.0).fillna(0.0)
    strength_score = strength_percentile / 100.0
    columns: dict[str, object] = {
        "primary_regime": primary,
        "breakout_direction": direction,
        "confidence": strength_score,
        "regime_strength_score": strength_score,
        "regime_strength_percentile": strength_percentile,
        "regime_score_source": "ema_gap_strength_percentile_rank",
        "reason": reason,
        "coiling": features["coiling"].fillna(False).astype(bool),
        "bbwp_percentile": features["bbwp_percentile"],
        "compression_ready": features["compression"].shift(1).fillna(False),
        "ema_gap_bps_signed": features["ema_gap_bps_signed"],
        "rsi": momentum["rsi"],
        "rsi_ema": momentum["rsi_ema"],
        "rsi_cross_direction": momentum["rsi_cross_direction"],
        "tactical_breakout_direction": tactical,
        "breakout_volume_ratio": breakout["volume_ratio"],
        "prior_range_high": breakout["prior_high"],
        "prior_range_low": breakout["prior_low"],
    }
    columns.update(_range_diagnostic_columns(features, config))
    return pd.DataFrame(columns, index=primary.index)


def _range_diagnostic_columns(
    features: pd.DataFrame,
    config: RegimeClassifierConfig,
) -> dict[str, object]:
    """Expose the exact causal predicates used by the range classifier."""
    weak = features["strength_rank"] <= config.range_strength_percentile
    insufficient_gap = features["strength_bps"] < config.minimum_trend_gap_bps
    return {
        "range_cause_coiling": features["coiling"].fillna(False).astype(bool),
        "range_cause_strength": weak.fillna(False).astype(bool),
        "range_cause_gap": insufficient_gap.fillna(False).astype(bool),
        "range_cause_filter": features["range_filter_active"].astype(bool),
        "range_filter_name": config.range_filter,
        "bbwp_compression_threshold": config.bbwp_compression_threshold,
        "minimum_trend_gap_bps": config.minimum_trend_gap_bps,
        "range_strength_threshold": config.range_strength_percentile,
        "trend_strength_threshold": config.trend_strength_percentile,
        "breakout_volume_multiple": config.breakout_volume_multiple,
    }


def classify_timeframe(
    df: pd.DataFrame,
    config: RegimeClassifierConfig | None = None,
) -> pd.DataFrame:
    """Classify completed bars without using any future value."""
    validate_regime_bars(df)
    cfg = config or RegimeClassifierConfig()
    features = _structure_features(df, cfg)
    breakout = _breakout_features(df, cfg)
    momentum = _momentum_features(df["close"].astype(float), cfg)
    primary = _assign_primary(features, breakout, cfg)
    direction = pd.Series(None, index=df.index, dtype=object)
    direction = direction.mask(breakout["upward"], BreakoutDirection.UPWARD.value)
    direction = direction.mask(breakout["downward"], BreakoutDirection.DOWNWARD.value)
    direction = direction.where(primary == PrimaryRegime.BREAKOUT.value, None)
    tactical = _tactical_direction(direction, features, momentum, cfg)
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
    return _classification_frame(
        primary,
        direction,
        features,
        momentum,
        breakout,
        tactical,
        reason,
        cfg,
    )
