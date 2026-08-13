"""Causal completed-bar signals for repaired Apex-derived candidates."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from hypervector.research.apex_directional_signals import _validated_bars


@dataclass(frozen=True)
class MeanReversionConfig:
    """Parameters for deviation entries and explicit reversion exits."""

    lookback: int = 20
    entry_z: float = 2.0
    exit_z: float = 0.5
    invalidation_z: float = 4.0
    pressure_threshold: float = 0.1
    minimum_std_bps: float = 1.0

    def __post_init__(self) -> None:
        if self.lookback < 3:
            raise ValueError("mean-reversion lookback must be at least three")
        if not 0.0 < self.exit_z < self.entry_z < self.invalidation_z:
            raise ValueError("mean-reversion z thresholds must be ordered")
        if self.pressure_threshold < 0.0 or self.minimum_std_bps <= 0.0:
            raise ValueError(
                "mean-reversion pressure and standard deviation must be positive"
            )


@dataclass(frozen=True)
class OITrendConfig:
    """Parameters for interval price, OI, and volume agreement."""

    lookback: int = 24
    volume_lookback: int = 36
    price_change_bps: float = 80.0
    oi_change_bps: float = 50.0
    volume_surge_mult: float = 1.3
    maximum_context_age_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.lookback < 2 or self.volume_lookback < 2:
            raise ValueError("OI trend lookbacks must be at least two")
        if self.price_change_bps <= 0.0 or self.oi_change_bps <= 0.0:
            raise ValueError("OI trend change thresholds must be positive")
        if self.volume_surge_mult <= 0.0:
            raise ValueError("OI trend volume multiplier must be positive")
        if self.maximum_context_age_seconds < 0.0:
            raise ValueError("OI context age must be non-negative")


def build_apex_mean_reversion_v2(
    bars: pd.DataFrame,
    books: pd.DataFrame,
    config: MeanReversionConfig = MeanReversionConfig(),
) -> pd.DataFrame:
    """Return fresh deviation entries and explicit long/short exit conditions."""
    clean = _validated_bars(bars)
    pressure = _aligned_numeric(
        books,
        "imbalance_5_delta_60s",
        clean.index,
    )
    prior_mean = clean["close"].shift(1).rolling(config.lookback).mean()
    prior_std = clean["close"].shift(1).rolling(config.lookback).std(ddof=0)
    minimum_std = prior_mean.mul(config.minimum_std_bps / 10_000.0)
    effective_std = prior_std.where(prior_std.gt(minimum_std), minimum_std)
    zscore = clean["close"].sub(prior_mean).div(effective_std)
    long_condition = zscore.le(-config.entry_z) & pressure.ge(config.pressure_threshold)
    short_condition = zscore.ge(config.entry_z) & pressure.le(
        -config.pressure_threshold
    )
    return pd.DataFrame(
        {
            "long_entry": _fresh_episode(long_condition),
            "short_entry": _fresh_episode(short_condition),
            "long_exit_mean": zscore.ge(-config.exit_z),
            "short_exit_mean": zscore.le(config.exit_z),
            "long_exit_invalidation": zscore.le(-config.invalidation_z),
            "short_exit_invalidation": zscore.ge(config.invalidation_z),
            "zscore": zscore,
            "pressure": pressure,
            "prior_mean": prior_mean,
            "prior_std": prior_std,
        },
        index=clean.index,
    )


def build_apex_oi_trend_v2(
    bars: pd.DataFrame,
    contexts: pd.DataFrame,
    config: OITrendConfig = OITrendConfig(),
) -> pd.DataFrame:
    """Return fresh price/OI agreement entries using true interval volume."""
    clean = _validated_bars(bars)
    oi = _aligned_numeric(contexts, "open_interest", clean.index)
    available_at = _aligned_timestamps(contexts, "available_at", clean.index)
    signal_at = pd.Series(clean.index + pd.Timedelta(minutes=5), index=clean.index)
    age_seconds = signal_at.sub(available_at).dt.total_seconds()
    oi_eligible = age_seconds.between(
        0.0,
        config.maximum_context_age_seconds,
        inclusive="both",
    ) & oi.gt(0.0)
    price_change = clean["close"].div(clean["close"].shift(config.lookback)).sub(1.0)
    oi_change = oi.div(oi.shift(config.lookback)).sub(1.0)
    prior_volume = clean["volume"].shift(1).rolling(config.volume_lookback).mean()
    volume_surge = clean["volume"].gt(prior_volume.mul(config.volume_surge_mult))
    price_threshold = config.price_change_bps / 10_000.0
    oi_threshold = config.oi_change_bps / 10_000.0
    long_condition = (
        oi_eligible
        & price_change.gt(price_threshold)
        & oi_change.gt(oi_threshold)
        & volume_surge
    )
    short_condition = (
        oi_eligible
        & price_change.lt(-price_threshold)
        & oi_change.lt(-oi_threshold)
        & volume_surge
    )
    return pd.DataFrame(
        {
            "long_entry": _fresh_episode(long_condition),
            "short_entry": _fresh_episode(short_condition),
            "long_exit_divergence": oi_eligible & oi_change.lt(-oi_threshold),
            "short_exit_divergence": oi_eligible & oi_change.gt(oi_threshold),
            "price_change_bps": price_change.mul(10_000.0),
            "oi_change_bps": oi_change.mul(10_000.0),
            "prior_volume_mean": prior_volume,
            "volume_surge": volume_surge,
            "oi_eligible": oi_eligible,
            "context_age_seconds": age_seconds,
        },
        index=clean.index,
    )


def _aligned_numeric(
    frame: pd.DataFrame,
    column: str,
    index: pd.Index,
) -> pd.Series:
    if column not in frame:
        raise ValueError(f"Apex cohort evidence missing column: {column}")
    if not frame.index.is_monotonic_increasing or not frame.index.is_unique:
        raise ValueError("Apex cohort evidence must be strictly ordered and unique")
    values = pd.to_numeric(frame[column], errors="coerce").reindex(index)
    return values.replace((np.inf, -np.inf), np.nan)


def _aligned_timestamps(
    frame: pd.DataFrame,
    column: str,
    index: pd.Index,
) -> pd.Series:
    if column not in frame:
        raise ValueError(f"Apex cohort evidence missing column: {column}")
    values = pd.to_datetime(frame[column], utc=True, errors="coerce")
    return pd.Series(values.to_numpy(), index=frame.index).reindex(index)


def _fresh_episode(condition: pd.Series) -> pd.Series:
    clean = condition.fillna(False).astype(bool)
    return clean & ~clean.shift(1, fill_value=False)
