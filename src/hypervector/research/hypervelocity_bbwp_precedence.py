"""Report-only challenger for hard 5m BBWP range precedence."""

from __future__ import annotations

import math

import pandas as pd

from hypervector.regime.classifier import RegimeClassifierConfig
from hypervector.regime.composite import (
    _completed_context,
    classify_multitimeframe,
)
from hypervector.regime.models import PrimaryRegime
from hypervector.research.hypervelocity_attribution import (
    compression_age_bars,
    regime_age_bars,
)

_DIRECTIONAL_STATES = (
    PrimaryRegime.TREND_UP.value,
    PrimaryRegime.TREND_DOWN.value,
)


def _validate_frames(
    decisions: pd.DataFrame,
    context_5m: pd.DataFrame,
) -> None:
    required_decisions = {
        "primary_regime",
        "state_5m",
        "structural_direction",
        "entry_direction",
        "reason",
    }
    missing = required_decisions.difference(decisions.columns)
    if missing:
        raise ValueError(f"BBWP decisions missing columns: {sorted(missing)}")
    required_context = {"primary_regime", "bbwp_percentile"}
    missing_context = required_context.difference(context_5m.columns)
    if missing_context:
        raise ValueError(f"BBWP 5m context missing columns: {sorted(missing_context)}")
    if not decisions.index.equals(context_5m.index):
        raise ValueError("BBWP decisions and 5m context require the same index")
    if not decisions["state_5m"].equals(context_5m["primary_regime"]):
        raise ValueError("BBWP decisions and 5m primary context disagree")


def apply_5m_bbwp_range_precedence(
    decisions: pd.DataFrame,
    context_5m: pd.DataFrame,
    *,
    threshold: float,
) -> pd.DataFrame:
    """Mask compressed 5m trends to RANGE without changing breakouts."""
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 100.0:
        raise ValueError("BBWP range threshold must be finite within [0, 100]")
    _validate_frames(decisions, context_5m)
    result = decisions.copy()
    percentile = context_5m["bbwp_percentile"].astype(float)
    compressed_trend = context_5m["primary_regime"].isin(
        _DIRECTIONAL_STATES
    ) & percentile.lt(threshold)
    result["bbwp_5m_percentile"] = percentile
    result["bbwp_5m_hard_range"] = compressed_trend
    result.loc[compressed_trend, "primary_regime"] = PrimaryRegime.RANGE.value
    result.loc[compressed_trend, "state_5m"] = PrimaryRegime.RANGE.value
    result.loc[compressed_trend, "structural_direction"] = None
    result.loc[compressed_trend, "entry_direction"] = None
    result.loc[compressed_trend, "reason"] = "5m_bbwp_compression_range"
    return result


def apply_1m_bbwp_recovery_delay(
    decisions: pd.DataFrame,
    *,
    threshold: float,
    minimum_age_bars: int,
) -> pd.DataFrame:
    """Delay entries after compression without changing structural state."""
    if (
        isinstance(minimum_age_bars, bool)
        or not isinstance(minimum_age_bars, int)
        or minimum_age_bars < 0
    ):
        raise ValueError("minimum_age_bars must be a non-negative integer")
    required = {"entry_direction", "bbwp_percentile"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"BBWP recovery decisions missing columns: {sorted(missing)}")
    result = decisions.copy()
    age = compression_age_bars(
        result["bbwp_percentile"].astype(float),
        threshold=threshold,
    )
    waiting = age.notna() & age.lt(minimum_age_bars)
    result["bbwp_1m_compression_age_bars"] = age
    result["bbwp_1m_recovery_wait"] = waiting
    result.loc[waiting, "entry_direction"] = None
    return result


def apply_1m_trend_breakout_confirmation(
    decisions: pd.DataFrame,
) -> pd.DataFrame:
    """Confirm a directional 5m breakout with a same-direction 1m trend."""
    required = {
        "state_1m",
        "state_5m",
        "structural_direction",
        "entry_direction",
        "reason",
    }
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(
            f"1m trend breakout confirmation missing columns: {sorted(missing)}"
        )
    result = decisions.copy()
    awaiting = result["state_5m"].eq(PrimaryRegime.BREAKOUT.value)
    awaiting &= result["entry_direction"].isna()
    awaiting &= result["reason"].eq("5m_breakout_awaiting_1m_confirmation")
    long_confirmation = result["structural_direction"].eq("long")
    long_confirmation &= result["state_1m"].eq(PrimaryRegime.TREND_UP.value)
    short_confirmation = result["structural_direction"].eq("short")
    short_confirmation &= result["state_1m"].eq(PrimaryRegime.TREND_DOWN.value)
    confirmed = awaiting & (long_confirmation | short_confirmation)
    result["breakout_confirmed_by_1m_trend"] = confirmed
    result.loc[confirmed, "entry_direction"] = result.loc[
        confirmed, "structural_direction"
    ]
    result.loc[confirmed, "reason"] = "5m_breakout_confirmed_by_1m_trend"
    return result


def apply_prefer_1m_direction_fusion(decisions: pd.DataFrame) -> pd.DataFrame:
    """Prefer a directional completed 1m state, otherwise retain the 5m entry."""
    required = {"state_1m", "entry_direction"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(
            f"direction-fusion decisions missing columns: {sorted(missing)}"
        )
    result = decisions.copy()
    original = result["entry_direction"].copy()
    fused_direction = original.astype(object)
    one_minute_long = result["state_1m"].eq(PrimaryRegime.TREND_UP.value)
    one_minute_short = result["state_1m"].eq(PrimaryRegime.TREND_DOWN.value)
    one_minute_directional = one_minute_long | one_minute_short
    canonical_directional = original.isin(("long", "short"))
    fused_direction.loc[one_minute_long] = "long"
    fused_direction.loc[one_minute_short] = "short"
    fused_direction.loc[fused_direction.isna()] = None
    result["entry_direction"] = fused_direction
    source = pd.Series("none", index=result.index, dtype="object")
    source.loc[canonical_directional] = "5m"
    source.loc[one_minute_directional] = "1m"
    result["direction_fusion_source"] = source
    result["direction_fusion_overrode_5m"] = (
        one_minute_directional
        & canonical_directional
        & result["entry_direction"].ne(original)
    )
    return result


def apply_breakout_onset_confirmation(decisions: pd.DataFrame) -> pd.DataFrame:
    """Confirm only a 5m breakout onset directly following hard range."""
    required = {
        "state_1m",
        "state_5m",
        "structural_direction",
        "entry_direction",
        "reason",
        "bbwp_5m_hard_range",
    }
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"breakout-onset decisions missing columns: {sorted(missing)}")
    if decisions.index.has_duplicates or not decisions.index.is_monotonic_increasing:
        raise ValueError("breakout-onset decisions require a unique increasing index")
    result = decisions.copy()
    previous_hard_range = result["bbwp_5m_hard_range"].shift(1, fill_value=False)
    awaiting = result["state_5m"].eq(PrimaryRegime.BREAKOUT.value)
    awaiting &= previous_hard_range.astype(bool)
    awaiting &= result["entry_direction"].isna()
    awaiting &= result["reason"].eq("5m_breakout_awaiting_1m_confirmation")
    long_confirmation = result["structural_direction"].eq("long")
    long_confirmation &= result["state_1m"].eq(PrimaryRegime.TREND_UP.value)
    short_confirmation = result["structural_direction"].eq("short")
    short_confirmation &= result["state_1m"].eq(PrimaryRegime.TREND_DOWN.value)
    confirmed = awaiting & (long_confirmation | short_confirmation)
    result["breakout_confirmed_at_range_onset"] = confirmed
    result.loc[confirmed, "entry_direction"] = result.loc[
        confirmed, "structural_direction"
    ]
    result.loc[confirmed, "reason"] = "5m_breakout_confirmed_at_range_onset"
    return result


def apply_regime_entry_age_limit(
    decisions: pd.DataFrame,
    *,
    maximum_age_exclusive: int,
) -> pd.DataFrame:
    """Mask late entries without changing the canonical structural regime."""
    if (
        isinstance(maximum_age_exclusive, bool)
        or not isinstance(maximum_age_exclusive, int)
        or maximum_age_exclusive < 1
    ):
        raise ValueError("maximum_age_exclusive must be a positive integer")
    required = {"state_5m", "entry_direction"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"regime age decisions missing columns: {sorted(missing)}")
    result = decisions.copy()
    age = regime_age_bars(result["state_5m"])
    blocked = age.ge(maximum_age_exclusive) & result["entry_direction"].notna()
    result["regime_age_5m_bars"] = age
    result["regime_entry_age_blocked"] = blocked
    result.loc[blocked, "entry_direction"] = None
    return result


def apply_regime_entry_minimum_age(
    decisions: pd.DataFrame,
    *,
    minimum_age_inclusive: int,
) -> pd.DataFrame:
    """Mask immature entries without changing the canonical structural regime."""
    if (
        isinstance(minimum_age_inclusive, bool)
        or not isinstance(minimum_age_inclusive, int)
        or minimum_age_inclusive < 1
    ):
        raise ValueError("minimum_age_inclusive must be a positive integer")
    required = {"state_5m", "entry_direction"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(
            f"minimum regime age decisions missing columns: {sorted(missing)}"
        )
    result = decisions.copy()
    age = regime_age_bars(result["state_5m"])
    blocked = age.lt(minimum_age_inclusive) & result["entry_direction"].notna()
    result["regime_age_5m_bars"] = age
    result["regime_entry_minimum_age_blocked"] = blocked
    result.loc[blocked, "entry_direction"] = None
    return result


def apply_fresh_opposed_context_confirmation(
    decisions: pd.DataFrame,
    *,
    confirmation_bars: int,
) -> pd.DataFrame:
    """Delay only newly changed 5m entries opposed by directional 15m context."""
    if (
        isinstance(confirmation_bars, bool)
        or not isinstance(confirmation_bars, int)
        or confirmation_bars < 1
    ):
        raise ValueError("confirmation_bars must be a positive integer")
    required = {"state_5m", "context_15m", "entry_direction"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(
            f"fresh opposed confirmation decisions missing: {sorted(missing)}"
        )
    if decisions.index.has_duplicates or not decisions.index.is_monotonic_increasing:
        raise ValueError(
            "fresh opposed confirmation requires a unique increasing index"
        )
    result = decisions.copy()
    age = regime_age_bars(result["state_5m"])
    direction = result["entry_direction"]
    context = result["context_15m"]
    opposed = direction.eq("long") & context.eq(PrimaryRegime.TREND_DOWN.value)
    opposed |= direction.eq("short") & context.eq(PrimaryRegime.TREND_UP.value)
    waiting = direction.notna() & opposed & age.lt(confirmation_bars)
    result["regime_age_5m_bars"] = age
    result["fresh_opposed_context_wait"] = waiting
    result.loc[waiting, "entry_direction"] = None
    return result


def apply_weak_opposed_strength_delay(
    decisions: pd.DataFrame,
    *,
    minimum_strength_percentile: float,
) -> pd.DataFrame:
    """Delay weak counter-context entries without rewriting published regimes."""
    threshold = float(minimum_strength_percentile)
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 100.0:
        raise ValueError("minimum_strength_percentile must be finite within [0, 100]")
    required = {
        "context_15m",
        "entry_direction",
        "regime_strength_percentile",
    }
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"weak opposed strength decisions missing: {sorted(missing)}")
    result = decisions.copy()
    strength = pd.to_numeric(
        result["regime_strength_percentile"], errors="raise"
    ).astype(float)
    observed = strength.dropna()
    if not observed.map(math.isfinite).all() or not observed.between(0.0, 100.0).all():
        raise ValueError("regime strength percentile must be within [0, 100]")
    direction = result["entry_direction"]
    context = result["context_15m"]
    opposed = direction.eq("long") & context.eq(PrimaryRegime.TREND_DOWN.value)
    opposed |= direction.eq("short") & context.eq(PrimaryRegime.TREND_UP.value)
    waiting = direction.notna() & opposed & (strength.isna() | strength.lt(threshold))
    result["weak_opposed_strength_wait"] = waiting
    result.loc[waiting, "entry_direction"] = None
    return result


def _release_age(hard_range: pd.Series) -> pd.Series:
    age: int | None = None
    values: list[float] = []
    for compressed in hard_range:
        if bool(compressed):
            age = 0
        elif age is not None:
            age += 1
        values.append(float(age) if age is not None else float("nan"))
    return pd.Series(values, index=hard_range.index, dtype="float64")


def apply_5m_compression_release_confirmation(
    decisions: pd.DataFrame,
    *,
    confirmation_bars: int,
) -> pd.DataFrame:
    """Expose a causal TRANSITION interval after hard 5m compression releases."""
    if (
        isinstance(confirmation_bars, bool)
        or not isinstance(confirmation_bars, int)
        or confirmation_bars < 1
    ):
        raise ValueError("confirmation_bars must be a positive integer")
    required = {
        "primary_regime",
        "state_5m",
        "structural_direction",
        "entry_direction",
        "reason",
        "bbwp_5m_hard_range",
    }
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"release confirmation missing columns: {sorted(missing)}")
    hard_range = decisions["bbwp_5m_hard_range"]
    if hard_range.isna().any():
        raise ValueError("release confirmation hard-range flags cannot be missing")
    result = decisions.copy()
    age = _release_age(hard_range)
    waiting = age.between(1.0, float(confirmation_bars), inclusive="both")
    waiting &= result["structural_direction"].isin(("long", "short"))
    result["bbwp_5m_release_age_bars"] = age
    result["bbwp_5m_release_wait"] = waiting
    result.loc[waiting, "primary_regime"] = PrimaryRegime.TRANSITION.value
    result.loc[waiting, "state_5m"] = PrimaryRegime.TRANSITION.value
    result.loc[waiting, "structural_direction"] = None
    result.loc[waiting, "entry_direction"] = None
    result.loc[waiting, "reason"] = "5m_bbwp_release_confirmation"
    return result


def classify_with_5m_bbwp_range_precedence(
    bars: pd.DataFrame,
    config: RegimeClassifierConfig,
) -> pd.DataFrame:
    """Return a causal hard-range challenger without altering runtime code."""
    if config.range_filter != "bbwp":
        raise ValueError("BBWP precedence challenger requires range_filter=bbwp")
    decisions = classify_multitimeframe(bars, config=config)
    context_5m = _completed_context(bars, bars.index, 5, config)
    return apply_5m_bbwp_range_precedence(
        decisions,
        context_5m,
        threshold=config.bbwp_compression_threshold,
    )
