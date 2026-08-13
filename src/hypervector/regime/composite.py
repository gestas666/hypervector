"""Causal 1m/5m/15m regime composition for Hypervelocity."""

from __future__ import annotations

import pandas as pd

from hypervector.regime.classifier import RegimeClassifierConfig, classify_timeframe
from hypervector.regime.models import BreakoutDirection, PrimaryRegime


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
    direction_1m = tf_1m["breakout_direction"]
    same_direction = direction_1m.eq(tf_5m["breakout_direction"])
    directional = direction_1m.notna()
    both_breakout = tf_1m["primary_regime"].eq(PrimaryRegime.BREAKOUT.value) & tf_5m[
        "primary_regime"
    ].eq(PrimaryRegime.BREAKOUT.value)
    return both_breakout & same_direction & directional


def _column(frame: pd.DataFrame, name: str, default: object) -> pd.Series:
    if name in frame.columns:
        return frame[name]
    return pd.Series(default, index=frame.index)


def _structural_direction(tf_5m: pd.DataFrame) -> pd.Series:
    primary = tf_5m["primary_regime"]
    breakout = tf_5m["breakout_direction"]
    direction = pd.Series(None, index=tf_5m.index, dtype=object)
    direction = direction.mask(primary.eq(PrimaryRegime.TREND_UP.value), "long")
    direction = direction.mask(primary.eq(PrimaryRegime.TREND_DOWN.value), "short")
    is_breakout = primary.eq(PrimaryRegime.BREAKOUT.value)
    direction = direction.mask(
        is_breakout & breakout.eq(BreakoutDirection.UPWARD.value), "long"
    )
    return direction.mask(
        is_breakout & breakout.eq(BreakoutDirection.DOWNWARD.value), "short"
    )


def _entry_direction(
    tf_5m: pd.DataFrame,
    structural: pd.Series,
    confirmed_breakout: pd.Series,
) -> pd.Series:
    primary = tf_5m["primary_regime"]
    trend = primary.isin([PrimaryRegime.TREND_UP.value, PrimaryRegime.TREND_DOWN.value])
    return structural.where(trend | confirmed_breakout, None)


def _tactical_columns(tf_1m: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "bbwp_percentile": _column(tf_1m, "bbwp_percentile", float("nan")),
        "compression_ready": _column(tf_1m, "compression_ready", False),
        "ema_gap_bps_signed": _column(tf_1m, "ema_gap_bps_signed", float("nan")),
        "rsi": _column(tf_1m, "rsi", float("nan")),
        "rsi_ema": _column(tf_1m, "rsi_ema", float("nan")),
        "rsi_cross_direction": _column(tf_1m, "rsi_cross_direction", None),
        "tactical_breakout_direction": _column(
            tf_1m, "tactical_breakout_direction", None
        ),
        "breakout_volume_ratio": _column(tf_1m, "breakout_volume_ratio", float("nan")),
        "prior_range_high": _column(tf_1m, "prior_range_high", float("nan")),
        "prior_range_low": _column(tf_1m, "prior_range_low", float("nan")),
    }


def _regime_diagnostic_columns(
    frame: pd.DataFrame,
    timeframe: str,
) -> dict[str, pd.Series]:
    """Prefix one causal classifier frame for unambiguous telemetry."""
    fields: tuple[tuple[str, str, object], ...] = (
        ("reason", "reason", "unavailable"),
        ("regime_strength_percentile", "strength_percentile", float("nan")),
        ("bbwp_percentile", "bbwp_percentile", float("nan")),
        ("ema_gap_bps_signed", "ema_gap_bps", float("nan")),
        ("rsi", "rsi", float("nan")),
        ("rsi_ema", "rsi_ema", float("nan")),
        ("rsi_cross_direction", "rsi_cross_direction", None),
        ("coiling", "coiling", False),
        ("range_cause_coiling", "range_cause_coiling", False),
        ("range_cause_strength", "range_cause_strength", False),
        ("range_cause_gap", "range_cause_gap", False),
        ("range_cause_filter", "range_cause_filter", False),
        ("breakout_volume_ratio", "breakout_volume_ratio", float("nan")),
    )
    return {
        f"regime_{timeframe}_{target}": _column(frame, source, default)
        for source, target, default in fields
    }


def _regime_contract_columns(tf_5m: pd.DataFrame) -> dict[str, pd.Series]:
    """Expose classifier thresholds once from the authoritative 5m frame."""
    fields: tuple[tuple[str, str, object], ...] = (
        ("range_filter_name", "regime_range_filter_name", "unavailable"),
        ("bbwp_compression_threshold", "regime_bbwp_threshold_pct", float("nan")),
        ("minimum_trend_gap_bps", "regime_minimum_gap_bps", float("nan")),
        (
            "range_strength_threshold",
            "regime_range_strength_threshold_pct",
            float("nan"),
        ),
        (
            "trend_strength_threshold",
            "regime_trend_strength_threshold_pct",
            float("nan"),
        ),
        ("breakout_volume_multiple", "regime_breakout_volume_multiple", float("nan")),
    )
    return {
        target: _column(tf_5m, source, default) for source, target, default in fields
    }


def _composite_frame(
    tf_1m: pd.DataFrame,
    tf_5m: pd.DataFrame,
    tf_15m: pd.DataFrame,
    primary: pd.Series,
    direction: pd.Series,
    structural: pd.Series,
    entry_direction: pd.Series,
    strength_score: pd.Series,
    reason: pd.Series,
) -> pd.DataFrame:
    columns: dict[str, object] = {
        "primary_regime": primary,
        "breakout_direction": direction,
        "structural_direction": structural,
        "entry_direction": entry_direction,
        "state_1m": tf_1m["primary_regime"],
        "state_5m": tf_5m["primary_regime"],
        "context_15m": tf_15m["primary_regime"],
        "confidence": strength_score,
        "regime_strength_score": strength_score,
        "regime_strength_percentile": strength_score * 100.0,
        "regime_score_source": "mean_multitimeframe_ema_gap_strength_percentile_rank",
        "reason": reason,
    }
    columns.update(_tactical_columns(tf_1m))
    columns.update(_regime_diagnostic_columns(tf_1m, "1m"))
    columns.update(_regime_diagnostic_columns(tf_5m, "5m"))
    columns.update(_regime_diagnostic_columns(tf_15m, "15m"))
    columns.update(_regime_contract_columns(tf_5m))
    return pd.DataFrame(columns, index=tf_1m.index)


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
    structural = _structural_direction(tf_5m)
    entry_direction = _entry_direction(tf_5m, structural, breakout)
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
    return _composite_frame(
        tf_1m,
        tf_5m,
        tf_15m,
        primary,
        direction,
        structural,
        entry_direction,
        strength_score,
        reason,
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
