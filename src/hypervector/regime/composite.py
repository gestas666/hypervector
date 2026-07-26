"""Causal 1m/5m/15m regime composition for Hypervelocity."""

from __future__ import annotations

import pandas as pd

from hypervector.regime.classifier import RegimeClassifierConfig, classify_timeframe
from hypervector.regime.models import PrimaryRegime


def _validate_cadence(df: pd.DataFrame, minutes: int, label: str) -> None:
    if df.empty:
        return
    expected = pd.Timedelta(minutes=minutes)
    aligned = df.index.floor(f"{minutes}min").equals(df.index)
    regular = (
        len(df.index) < 2 or df.index.to_series().diff().iloc[1:].eq(expected).all()
    )
    if not aligned or not regular:
        raise ValueError(
            f"{label} regime bars require exact {minutes}m open-time cadence"
        )


def _strength_score(frame: pd.DataFrame) -> pd.Series:
    return frame.get("regime_strength_score", frame["confidence"]).astype(float)


def _resample_bars(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    grouped = df.resample(f"{minutes}min", label="left", closed="left")
    aggregated = grouped.agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    complete = grouped["close"].count().eq(minutes)
    aggregated = aggregated.loc[complete].dropna()
    aggregated.index = aggregated.index + pd.Timedelta(minutes=minutes - 1)
    return aggregated


def _completed_context(
    df: pd.DataFrame,
    index: pd.DatetimeIndex,
    minutes: int,
    config: RegimeClassifierConfig,
) -> pd.DataFrame:
    classified = classify_timeframe(_resample_bars(df, minutes), config)
    return classified.reindex(index, method="ffill").fillna(
        {
            "primary_regime": PrimaryRegime.UNKNOWN.value,
            "confidence": 0.0,
            "regime_strength_score": 0.0,
            "regime_strength_percentile": 0.0,
            "reason": "warmup_incomplete",
            "coiling": False,
        }
    )


def _completed_supplied_context(
    bars: pd.DataFrame,
    index: pd.DatetimeIndex,
    config: RegimeClassifierConfig,
    *,
    minutes: int,
) -> pd.DataFrame:
    classified = classify_timeframe(bars, config)
    classified.index = classified.index + pd.Timedelta(minutes=minutes - 1)
    return classified.reindex(index, method="ffill").fillna(
        {
            "primary_regime": PrimaryRegime.UNKNOWN.value,
            "confidence": 0.0,
            "regime_strength_score": 0.0,
            "regime_strength_percentile": 0.0,
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
    direction = pd.Series(None, index=tf_1m.index, dtype=object)
    reason = pd.Series("5m_primary_state", index=tf_1m.index, dtype=object)
    trend = primary.isin([PrimaryRegime.TREND_UP.value, PrimaryRegime.TREND_DOWN.value])
    reason = reason.mask(trend, "5m_primary_trend")
    awaiting_breakout = primary.eq(PrimaryRegime.BREAKOUT.value) & ~breakout
    reason = reason.mask(
        awaiting_breakout,
        "5m_breakout_awaiting_1m_confirmation",
    )
    primary = primary.mask(breakout, PrimaryRegime.BREAKOUT.value)
    direction = direction.mask(breakout, tf_1m["breakout_direction"])
    reason = reason.mask(breakout, "confirmed_1m_5m_breakout")
    strength_score = pd.concat(
        [_strength_score(tf_1m), _strength_score(tf_5m), _strength_score(tf_15m)],
        axis=1,
    ).mean(axis=1)
    return pd.DataFrame(
        {
            "primary_regime": primary,
            "breakout_direction": direction,
            "state_1m": tf_1m["primary_regime"],
            "state_5m": tf_5m["primary_regime"],
            "context_15m": tf_15m["primary_regime"],
            "confidence": strength_score,
            "regime_strength_score": strength_score,
            "regime_strength_percentile": strength_score * 100.0,
            "regime_score_source": (
                "mean_multitimeframe_ema_gap_strength_percentile_rank"
            ),
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
    _validate_cadence(df_1m, 1, "1m")
    if df_5m is not None:
        _validate_cadence(df_5m, 5, "5m")
    if df_15m is not None:
        _validate_cadence(df_15m, 15, "15m")
    tf_1m = classify_timeframe(df_1m, cfg)
    tf_5m = (
        _completed_context(df_1m, df_1m.index, 5, cfg)
        if df_5m is None
        else _completed_supplied_context(df_5m, df_1m.index, cfg, minutes=5)
    )
    tf_15m = (
        _completed_context(df_1m, df_1m.index, 15, cfg)
        if df_15m is None
        else _completed_supplied_context(df_15m, df_1m.index, cfg, minutes=15)
    )
    return compose_regimes(tf_1m, tf_5m, tf_15m)
