"""Source and execution contracts for the entry-filter factorial."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import math

import pandas as pd

from hypervector.research.hypervelocity_bbwp_precedence import (
    apply_1m_bbwp_recovery_delay,
    apply_5m_bbwp_range_precedence,
)
from hypervector.research.maker_replay_models import (
    MakerReplayConfig,
    MakerReplayLifecycle,
    MakerReplayReport,
)

ENTRY_FILTER_CANDIDATES = (
    "canonical_control",
    "hard_bbwp_only",
    "recovery6_only",
    "hard_bbwp_recovery6",
)
STRENGTH_FOLLOWUP_CANDIDATES = (
    "hard_bbwp_recovery6_control",
    "hard_bbwp_recovery6_strength50",
)


def entry_filter_decision_grid(
    canonical: pd.DataFrame,
    context_5m: pd.DataFrame,
    *,
    compression_threshold: float,
    recovery_age_bars: int,
) -> dict[str, pd.DataFrame]:
    """Return the frozen 2x2 hard-BBWP and recovery decision factorial."""
    hard = apply_5m_bbwp_range_precedence(
        canonical,
        context_5m,
        threshold=compression_threshold,
    )
    recovery = apply_1m_bbwp_recovery_delay(
        canonical,
        threshold=compression_threshold,
        minimum_age_bars=recovery_age_bars,
    )
    combined = apply_1m_bbwp_recovery_delay(
        hard,
        threshold=compression_threshold,
        minimum_age_bars=recovery_age_bars,
    )
    return {
        "canonical_control": canonical.copy(),
        "hard_bbwp_only": hard,
        "recovery6_only": recovery,
        "hard_bbwp_recovery6": combined,
    }


def apply_minimum_entry_strength(
    decisions: pd.DataFrame,
    *,
    minimum: float,
) -> pd.DataFrame:
    """Mask entries below a research-only regime-strength threshold."""
    if not math.isfinite(minimum) or not 0.0 <= minimum <= 100.0:
        raise ValueError("minimum entry strength must be finite and within [0, 100]")
    required = {"entry_direction", "regime_strength_percentile", "reason"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"minimum-strength decisions missing: {sorted(missing)}")
    output = decisions.copy()
    output["entry_direction"] = output["entry_direction"].astype(object)
    strength = pd.to_numeric(output["regime_strength_percentile"], errors="coerce")
    directional = output["entry_direction"].notna()
    wait = directional & (strength.isna() | strength.lt(minimum))
    output["minimum_entry_strength_wait"] = wait
    output.loc[wait, "entry_direction"] = None
    output.loc[wait, "reason"] = "minimum_entry_strength_wait"
    return output


def _replay_config() -> MakerReplayConfig:
    return MakerReplayConfig(
        initial_equity=10_000.0,
        maker_fee_rate=0.00015,
        taker_fee_rate=0.00045,
        fill_rule="trade-through",
        entry_ttl_seconds=300.0,
        reentry_cooldown_seconds=300.0,
        same_direction_reentry_policy="regime_reset",
    )


def entry_filter_candidate_configs() -> dict[str, MakerReplayConfig]:
    """Return execution-identical configs for the four decision candidates."""
    return {name: _replay_config() for name in ENTRY_FILTER_CANDIDATES}


def strength_followup_candidate_configs() -> dict[str, MakerReplayConfig]:
    """Return execution-identical configs for the strength follow-up pair."""
    return {name: _replay_config() for name in STRENGTH_FOLLOWUP_CANDIDATES}


def _source_frame(positions: pd.DataFrame) -> pd.DataFrame:
    required = {"open_time_utc", "side"}
    missing = required.difference(positions.columns)
    if missing:
        raise ValueError(f"entry-filter source positions missing: {sorted(missing)}")
    frame = positions.loc[:, ["open_time_utc", "side"]].copy()
    frame["event_time"] = pd.to_datetime(
        frame.pop("open_time_utc"), utc=True, format="ISO8601"
    )
    frame["side"] = frame["side"].astype(str).str.lower()
    if frame.empty or frame["event_time"].isna().any():
        raise ValueError("entry-filter source positions require valid timestamps")
    if not frame["side"].isin(("long", "short")).all():
        raise ValueError("entry-filter source sides must be long or short")
    return frame.sort_values("event_time", kind="stable").reset_index(drop=True)


def _aligned_decisions(
    decisions: pd.DataFrame,
    timestamps: pd.DatetimeIndex,
) -> pd.DataFrame:
    required = {
        "primary_regime",
        "state_5m",
        "structural_direction",
        "entry_direction",
        "reason",
    }
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"entry-filter decisions missing: {sorted(missing)}")
    index = decisions.index
    valid = isinstance(index, pd.DatetimeIndex) and index.tz is not None
    valid &= index.is_unique and index.is_monotonic_increasing
    if not valid:
        raise ValueError("entry-filter decisions require a causal DatetimeIndex")
    available = decisions.copy()
    available.index = available.index + pd.Timedelta(minutes=1)
    return available.reindex(timestamps, method="ffill")


def _no_candidate_reason(row: pd.Series) -> str:
    if bool(row.get("minimum_entry_strength_wait", False)):
        return "minimum_entry_strength_wait"
    if bool(row.get("bbwp_5m_hard_range", False)):
        return "hard_bbwp_range"
    if bool(row.get("bbwp_1m_recovery_wait", False)):
        return "recovery_delay"
    if row.get("state_5m") == "RANGE":
        return "canonical_range"
    if row.get("reason") == "5m_breakout_awaiting_1m_confirmation":
        return "strict_breakout_wait"
    return "other_no_candidate"


def _source_candidate_attribution(
    source: pd.DataFrame,
    decisions: pd.DataFrame,
) -> dict[str, object]:
    timestamps = pd.DatetimeIndex(source["event_time"])
    aligned = _aligned_decisions(decisions, timestamps)
    wanted = source["side"].to_numpy(dtype=object)
    predicted = aligned["entry_direction"].to_numpy(dtype=object)
    structural = aligned["structural_direction"].to_numpy(dtype=object)
    present = pd.notna(predicted)
    matches = present & (predicted == wanted)
    opposites = present & (predicted != wanted)
    structural_present = pd.notna(structural)
    structural_matches = structural_present & (structural == wanted)
    structural_opposites = structural_present & (structural != wanted)
    reasons = Counter(
        _no_candidate_reason(aligned.iloc[index])
        for index, value in enumerate(present)
        if not value
    )
    return {
        "source_entries": len(source),
        "direction_matches": int(matches.sum()),
        "direction_match_basis": "entry_direction",
        "opposite_directions": int(opposites.sum()),
        "no_candidate": int((~present).sum()),
        "structural_direction_matches": int(structural_matches.sum()),
        "structural_opposite_directions": int(structural_opposites.sum()),
        "structural_no_direction": int((~structural_present).sum()),
        "no_candidate_reasons": dict(sorted(reasons.items())),
        "false_range_at_entries": int(aligned["primary_regime"].eq("RANGE").sum()),
    }


def source_entry_attribution(
    positions: pd.DataFrame,
    decision_grid: Mapping[str, pd.DataFrame],
) -> dict[str, dict[str, object]]:
    """Attribute exact creator entry matches and missing-candidate reasons."""
    source = _source_frame(positions)
    return {
        name: _source_candidate_attribution(source, decisions)
        for name, decisions in decision_grid.items()
    }


def _filled_lifecycles(
    lifecycles: Sequence[MakerReplayLifecycle],
) -> list[tuple[pd.Timestamp, str]]:
    return sorted(
        (
            pd.Timestamp(row.entry_time_utc),
            row.direction,
        )
        for row in lifecycles
        if row.entry_time_utc is not None
    )


def _proximity_matches(
    source: pd.DataFrame,
    fills: list[tuple[pd.Timestamp, str]],
    maximum: pd.Timedelta,
) -> int:
    matches = 0
    for side in ("long", "short"):
        source_times = sorted(source.loc[source["side"].eq(side), "event_time"])
        fill_times = sorted(timestamp for timestamp, value in fills if value == side)
        source_index = 0
        fill_index = 0
        while source_index < len(source_times) and fill_index < len(fill_times):
            source_time = source_times[source_index]
            fill_time = fill_times[fill_index]
            if fill_time < source_time - maximum:
                fill_index += 1
            elif source_time < fill_time - maximum:
                source_index += 1
            else:
                matches += 1
                source_index += 1
                fill_index += 1
    return matches


def source_fill_proximity(
    positions: pd.DataFrame,
    report: MakerReplayReport,
) -> dict[str, int]:
    """Return one-to-one same-side source/fill matches by time tolerance."""
    source = _source_frame(positions)
    fills = _filled_lifecycles(report.lifecycles)
    return {
        f"{minutes}m": _proximity_matches(
            source,
            fills,
            pd.Timedelta(minutes=minutes),
        )
        for minutes in (5, 10, 30)
    }
