"""Canonical multi-timeframe regime policy for backend consumers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from hypervector.regime.classifier import RegimeClassifierConfig
from hypervector.regime.composite import classify_multitimeframe
from hypervector.regime.models import BreakoutDirection, PrimaryRegime

UltimateRegimeState = Literal[
    "TREND_UP",
    "TREND_DOWN",
    "BREAKOUT",
    "RANGE",
    "TRANSITION",
    "UNKNOWN",
]


@dataclass(frozen=True)
class RegimePolicy:
    """Entry policy derived from one canonical regime state."""

    state: UltimateRegimeState
    long_weight: float
    short_weight: float
    max_leverage: float
    allow_taker: bool
    recommended_exit_mode: str


def _entry_weights(classified: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    primary = classified["primary_regime"]
    breakout = classified["breakout_direction"]
    long_allowed = primary.eq(PrimaryRegime.TREND_UP.value) | (
        primary.eq(PrimaryRegime.BREAKOUT.value)
        & breakout.eq(BreakoutDirection.UPWARD.value)
    )
    short_allowed = primary.eq(PrimaryRegime.TREND_DOWN.value) | (
        primary.eq(PrimaryRegime.BREAKOUT.value)
        & breakout.eq(BreakoutDirection.DOWNWARD.value)
    )
    return long_allowed.astype(float), short_allowed.astype(float)


def detect_ultimate_regime(
    df_1m: pd.DataFrame,
    df_5m: pd.DataFrame | None = None,
    df_15m: pd.DataFrame | None = None,
    *,
    htf_resample_rule: str = "15min",
    config: RegimeClassifierConfig | None = None,
) -> pd.DataFrame:
    """Return canonical state and no-entry-safe policy from completed bars."""
    if htf_resample_rule != "15min" and df_15m is None:
        raise ValueError("custom HTF rules require an explicit df_15m frame")
    classified = classify_multitimeframe(
        df_1m,
        config=config,
        df_5m=df_5m,
        df_15m=df_15m,
    )
    long_weight, short_weight = _entry_weights(classified)
    allowed = (long_weight + short_weight) > 0.0
    return pd.DataFrame(
        {
            "regime_state": classified["primary_regime"],
            "breakout_direction": classified["breakout_direction"],
            "state_1m": classified["state_1m"],
            "state_5m": classified["state_5m"],
            "context_15m": classified["context_15m"],
            "regime_reason": classified["reason"],
            "confidence": classified["confidence"],
            "long_weight": long_weight,
            "short_weight": short_weight,
            "max_leverage": allowed.astype(float) * 40.0,
            "dynamic_leverage": allowed.astype(float) * 40.0,
            "allow_taker": False,
        },
        index=df_1m.index,
    )
