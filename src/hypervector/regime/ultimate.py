"""Canonical multi-timeframe regime policy for backend consumers."""

from __future__ import annotations

from typing import Literal

import pandas as pd

from hypervector.regime.classifier import RegimeClassifierConfig
from hypervector.regime.composite import classify_multitimeframe

UltimateRegimeState = Literal[
    "TREND_UP",
    "TREND_DOWN",
    "BREAKOUT",
    "RANGE",
    "TRANSITION",
    "UNKNOWN",
]


def _entry_weights(classified: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    direction = classified["entry_direction"]
    long_allowed = direction.eq("long")
    short_allowed = direction.eq("short")
    return long_allowed.astype(float), short_allowed.astype(float)


def detect_ultimate_regime(
    df_1m: pd.DataFrame,
    df_5m: pd.DataFrame | None = None,
    df_15m: pd.DataFrame | None = None,
    *,
    htf_resample_rule: str = "15min",
    config: RegimeClassifierConfig | None = None,
) -> pd.DataFrame:
    """Return canonical state and directional entry weights from completed bars.

    The output describes the market only; execution policy (leverage, order
    type) belongs to the strategy's declared execution options.
    """
    if htf_resample_rule != "15min" and df_15m is None:
        raise ValueError("custom HTF rules require an explicit df_15m frame")
    classified = classify_multitimeframe(
        df_1m,
        config=config,
        df_5m=df_5m,
        df_15m=df_15m,
    )
    long_weight, short_weight = _entry_weights(classified)
    return pd.DataFrame(
        {
            "regime_state": classified["primary_regime"],
            "breakout_direction": classified["breakout_direction"],
            "state_1m": classified["state_1m"],
            "state_5m": classified["state_5m"],
            "context_15m": classified["context_15m"],
            "regime_reason": classified["reason"],
            "confidence": classified["confidence"],
            "structural_direction": classified["structural_direction"],
            "entry_direction": classified["entry_direction"],
            "bbwp_percentile": classified["bbwp_percentile"],
            "compression_ready": classified["compression_ready"],
            "ema_gap_bps_signed": classified["ema_gap_bps_signed"],
            "rsi": classified["rsi"],
            "rsi_ema": classified["rsi_ema"],
            "rsi_cross_direction": classified["rsi_cross_direction"],
            "tactical_breakout_direction": classified["tactical_breakout_direction"],
            "breakout_volume_ratio": classified["breakout_volume_ratio"],
            "prior_range_high": classified["prior_range_high"],
            "prior_range_low": classified["prior_range_low"],
            "long_weight": long_weight,
            "short_weight": short_weight,
        },
        index=df_1m.index,
    )
