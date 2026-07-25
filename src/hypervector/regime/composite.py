"""Causal 1m/5m/15m regime composition for Hypervelocity."""

from __future__ import annotations

import pandas as pd

from hypervector.regime.classifier import RegimeClassifierConfig, classify_timeframe
from hypervector.regime.models import PrimaryRegime


def _resample_bars(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    return df.resample(f"{minutes}min", label="right", closed="right").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    ).dropna()


def _completed_context(
    df: pd.DataFrame,
    index: pd.DatetimeIndex,
    minutes: int,
    config: RegimeClassifierConfig,
) -> pd.DataFrame:
    classified = classify_timeframe(_resample_bars(df, minutes), config).shift(1)
    return classified.reindex(index, method="ffill").fillna(
        {
            "primary_regime": PrimaryRegime.UNKNOWN.value,
            "confidence": 0.0,
            "reason": "warmup_incomplete",
            "coiling": False,
        }
    )


def _completed_supplied_context(
    bars: pd.DataFrame,
    index: pd.DatetimeIndex,
    config: RegimeClassifierConfig,
) -> pd.DataFrame:
    classified = classify_timeframe(bars, config).shift(1)
    return classified.reindex(index, method="ffill").fillna(
        {
            "primary_regime": PrimaryRegime.UNKNOWN.value,
            "confidence": 0.0,
            "reason": "warmup_incomplete",
            "coiling": False,
        }
    )


def _confirmed_breakout(tf_1m: pd.DataFrame, tf_5m: pd.DataFrame) -> pd.Series:
    same_direction = tf_1m["breakout_direction"].eq(tf_5m["breakout_direction"])
    directional = tf_1m["breakout_direction"].notna()
    both_breakout = tf_1m["primary_regime"].eq(PrimaryRegime.BREAKOUT.value) & tf_5m[
        "primary_regime"
    ].eq(PrimaryRegime.BREAKOUT.value)
    return both_breakout & same_direction & directional


def compose_regimes(
    tf_1m: pd.DataFrame,
    tf_5m: pd.DataFrame,
    tf_15m: pd.DataFrame,
) -> pd.DataFrame:
    """Resolve canonical state with 5m primary and 15m non-veto context."""
    if not tf_1m.index.equals(tf_5m.index) or not tf_1m.index.equals(tf_15m.index):
        raise ValueError("regime frames must share the same index")
    breakout = _confirmed_breakout(tf_1m, tf_5m)
    primary = tf_5m["primary_regime"].copy()
    direction = tf_5m["breakout_direction"].copy()
    reason = pd.Series("5m_primary_state", index=tf_1m.index, dtype=object)
    directional_states = [PrimaryRegime.TREND_UP.value, PrimaryRegime.TREND_DOWN.value]
    fallback = ~primary.isin(directional_states + [PrimaryRegime.BREAKOUT.value])
    fallback &= tf_1m["primary_regime"].isin(directional_states)
    primary = primary.mask(fallback, tf_1m["primary_regime"])
    reason = reason.mask(fallback, "1m_directional_fallback")
    trend = primary.isin([PrimaryRegime.TREND_UP.value, PrimaryRegime.TREND_DOWN.value])
    reason = reason.mask(trend & ~fallback, "5m_primary_trend")
    primary = primary.mask(breakout, PrimaryRegime.BREAKOUT.value)
    direction = direction.mask(breakout, tf_1m["breakout_direction"])
    direction = direction.where(primary == PrimaryRegime.BREAKOUT.value, None)
    reason = reason.mask(breakout, "confirmed_1m_5m_breakout")
    confidence = pd.concat(
        [tf_1m["confidence"], tf_5m["confidence"], tf_15m["confidence"]], axis=1
    ).mean(axis=1)
    return pd.DataFrame(
        {
            "primary_regime": primary,
            "breakout_direction": direction,
            "state_1m": tf_1m["primary_regime"],
            "state_5m": tf_5m["primary_regime"],
            "context_15m": tf_15m["primary_regime"],
            "confidence": confidence,
            "reason": reason,
        },
        index=tf_1m.index,
    )


def classify_multitimeframe(
    df_1m: pd.DataFrame,
    config: RegimeClassifierConfig | None = None,
    df_5m: pd.DataFrame | None = None,
    df_15m: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Classify 1m execution bars with completed 5m and 15m context."""
    cfg = config or RegimeClassifierConfig()
    tf_1m = classify_timeframe(df_1m, cfg)
    tf_5m = (
        _completed_context(df_1m, df_1m.index, 5, cfg)
        if df_5m is None
        else _completed_supplied_context(df_5m, df_1m.index, cfg)
    )
    tf_15m = (
        _completed_context(df_1m, df_1m.index, 15, cfg)
        if df_15m is None
        else _completed_supplied_context(df_15m, df_1m.index, cfg)
    )
    return compose_regimes(tf_1m, tf_5m, tf_15m)
