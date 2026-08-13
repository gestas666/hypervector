"""Causal, report-only Hypertrader regime agreement candidates."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

import pandas as pd

from hypervector.research.hypervelocity_attribution import regime_age_bars

_PRIMARY_DIRECTIONS = {
    "TREND_UP": "long",
    "TREND_DOWN": "short",
}
_BREAKOUT_DIRECTIONS = {
    "BK_UPWARD": "long",
    "BK_DOWNWARD": "short",
}


def _causal_index(frame: pd.DataFrame, label: str) -> pd.DatetimeIndex:
    index = frame.index
    valid = isinstance(index, pd.DatetimeIndex) and index.tz is not None
    valid &= index.is_unique and index.is_monotonic_increasing
    if not valid:
        raise ValueError(f"{label} require a unique, ordered, timezone-aware index")
    return index


def _source_directions(labels: pd.DataFrame) -> pd.DataFrame:
    required = {"available_at", "primary_code", "secondary_code"}
    missing = required.difference(labels.columns)
    if missing:
        raise ValueError(f"source regime labels missing: {sorted(missing)}")
    source_index = _causal_index(labels, "source regime labels")
    available = pd.DatetimeIndex(pd.to_datetime(labels["available_at"], utc=True))
    if not available.is_unique or not available.is_monotonic_increasing:
        raise ValueError("source label availability must be unique and ordered")
    if not (available > source_index).all():
        raise ValueError("each source label must become available after its source bar")
    primary = labels["primary_code"].astype("string")
    secondary = labels["secondary_code"].astype("string")
    direction = primary.map(_PRIMARY_DIRECTIONS).astype(object)
    breakout = primary.eq("BREAKOUT")
    direction.loc[breakout] = secondary.loc[breakout].map(_BREAKOUT_DIRECTIONS)
    return pd.DataFrame(
        {
            "source_regime_available_at": available,
            "source_regime_primary": primary.to_numpy(dtype=object),
            "source_regime_secondary": secondary.to_numpy(dtype=object),
            "source_regime_direction": direction.to_numpy(dtype=object),
        },
        index=available,
    )


def _aligned_source(
    decisions: pd.DataFrame,
    labels: pd.DataFrame,
) -> pd.DataFrame:
    decision_index = _causal_index(decisions, "source-gate decisions")
    available = decision_index + pd.Timedelta(minutes=1)
    aligned = _source_directions(labels).reindex(available, method="ffill")
    aligned.index = decision_index
    return aligned


def apply_source_regime_agreement(
    decisions: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    revision: str,
) -> pd.DataFrame:
    """Keep canonical entries only when a causally available source label agrees."""
    if not revision:
        raise ValueError("source regime revision must be non-empty")
    required = {"entry_direction", "reason"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"source-gate decisions missing: {sorted(missing)}")
    output = decisions.copy()
    output["entry_direction"] = output["entry_direction"].astype(object)
    aligned = _aligned_source(decisions, labels)
    for column in aligned:
        output[column] = aligned[column]
    output["source_regime_revision"] = revision
    directional = output["entry_direction"].notna()
    unavailable = directional & output["source_regime_primary"].isna()
    non_tradable = directional & output["source_regime_direction"].isna()
    mismatch = (
        directional
        & ~non_tradable
        & (output["entry_direction"] != output["source_regime_direction"])
    )
    blocked = unavailable | non_tradable | mismatch
    output["source_regime_agreement_wait"] = blocked
    output.loc[unavailable, "reason"] = "source_regime_unavailable"
    output.loc[non_tradable & ~unavailable, "reason"] = "source_regime_not_tradable"
    output.loc[mismatch, "reason"] = "source_regime_direction_mismatch"
    output.loc[blocked, "entry_direction"] = None
    return output


def apply_source_regime_quality(decisions: pd.DataFrame) -> pd.DataFrame:
    """Exclude source states explicitly classified as weak and choppy."""
    required = {"entry_direction", "reason", "source_regime_secondary"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"source-quality decisions missing: {sorted(missing)}")
    output = decisions.copy()
    output["entry_direction"] = output["entry_direction"].astype(object)
    secondary = output["source_regime_secondary"].astype("string")
    waiting = output["entry_direction"].notna()
    waiting &= secondary.str.endswith("_WEAK_CHOPPY", na=False)
    output["source_regime_quality_wait"] = waiting
    output.loc[waiting, "entry_direction"] = None
    output.loc[waiting, "reason"] = "source_regime_weak_choppy"
    return output


def apply_source_regime_minimum_age(
    decisions: pd.DataFrame,
    *,
    minimum_age_minutes: int,
) -> pd.DataFrame:
    """Delay entries until a source primary regime persists for N minutes."""
    if (
        isinstance(minimum_age_minutes, bool)
        or not isinstance(minimum_age_minutes, int)
        or minimum_age_minutes < 0
    ):
        raise ValueError("source minimum age must be a non-negative integer")
    required = {"entry_direction", "reason", "source_regime_primary"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"source-age decisions missing: {sorted(missing)}")
    output = decisions.copy()
    output["entry_direction"] = output["entry_direction"].astype(object)
    age = regime_age_bars(output["source_regime_primary"])
    waiting = output["entry_direction"].notna() & age.lt(minimum_age_minutes)
    output["source_regime_age_minutes"] = age
    output["source_regime_confirmation_wait"] = waiting
    output.loc[waiting, "entry_direction"] = None
    output.loc[waiting, "reason"] = "source_regime_confirmation_wait"
    return output


def source_regime_agreement_grid(
    canonical: pd.DataFrame,
    label_revisions: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """Return an unchanged control plus one causal agreement candidate per source."""
    if not label_revisions:
        raise ValueError("at least one source regime revision is required")
    result = {"canonical_control": canonical.copy()}
    for revision, labels in label_revisions.items():
        name = f"{revision}_source_agreement"
        if name in result:
            raise ValueError(f"duplicate source regime candidate: {name}")
        result[name] = apply_source_regime_agreement(
            canonical,
            labels,
            revision=revision,
        )
    return result


def source_regime_quality_timing_grid(
    canonical: pd.DataFrame,
    strict_labels: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Return strict control plus independent quality and timing challengers."""
    control = apply_source_regime_agreement(
        canonical,
        strict_labels,
        revision="strict",
    )
    return {
        "strict_source_control": control,
        "strict_source_no_weak_choppy": apply_source_regime_quality(control),
        "strict_source_min_age4": apply_source_regime_minimum_age(
            control,
            minimum_age_minutes=4,
        ),
    }


def bound_decision_grid(
    decisions: Mapping[str, pd.DataFrame],
    *,
    start: datetime,
    end: datetime,
) -> dict[str, pd.DataFrame]:
    """Exclude causal warmup rows from every scored replay candidate."""
    if end <= start:
        raise ValueError("decision replay end must follow start")
    result: dict[str, pd.DataFrame] = {}
    for name, frame in decisions.items():
        index = _causal_index(frame, f"{name} decisions")
        result[name] = frame.loc[(index >= start) & (index < end)].copy()
    return result


def source_regime_interaction_grid(
    canonical: pd.DataFrame,
    hard_recovery: pd.DataFrame,
    strict_labels: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Return controls and their strict-source agreement interaction."""
    canonical_index = _causal_index(canonical, "canonical decisions")
    hard_index = _causal_index(hard_recovery, "hard-recovery decisions")
    if not canonical_index.equals(hard_index):
        raise ValueError("interaction decision indexes must match")
    return {
        "canonical_control": canonical.copy(),
        "hard_bbwp_recovery6_control": hard_recovery.copy(),
        "strict_source_agreement": apply_source_regime_agreement(
            canonical, strict_labels, revision="strict"
        ),
        "hard_bbwp_recovery6_strict_source_agreement": (
            apply_source_regime_agreement(
                hard_recovery,
                strict_labels,
                revision="strict",
            )
        ),
    }
