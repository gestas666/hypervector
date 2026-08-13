"""Point-in-time creator entry counts within structural regime episodes."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

import pandas as pd

_REQUIRED_POSITION_COLUMNS = {"open_ts", "side", "timestamp_provenance"}


def _validated_limits(limits: Sequence[int]) -> tuple[int, ...]:
    values = tuple(limits)
    if not values or any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in values
    ):
        raise ValueError("source episode limits must be positive integers")
    if len(values) != len(set(values)):
        raise ValueError("source episode limits must be unique")
    return values


def _episode_counts(
    logical: pd.DataFrame,
    decisions: pd.DataFrame,
) -> list[int]:
    missing = _REQUIRED_POSITION_COLUMNS.difference(logical.columns)
    if missing:
        raise ValueError(f"source episodes missing columns: {sorted(missing)}")
    if "structural_direction" not in decisions:
        raise ValueError("source episodes require structural_direction decisions")
    if not isinstance(decisions.index, pd.DatetimeIndex):
        raise ValueError("source episode decisions require a DatetimeIndex")
    structural = decisions["structural_direction"].astype(object).copy()
    structural.index = structural.index + pd.Timedelta(minutes=1)
    episodes = structural.ne(structural.shift()).cumsum().astype("int64")
    matched: Counter[tuple[int, str]] = Counter()
    for row in logical.itertuples(index=False):
        timestamp = pd.Timestamp(row.open_ts)
        position = int(structural.index.searchsorted(timestamp, side="right")) - 1
        if position < 0 or structural.iloc[position] != row.side:
            continue
        matched[(int(episodes.iloc[position]), str(row.side))] += 1
    return list(matched.values())


def _limit_compatibility(
    counts: Sequence[int],
    limits: Sequence[int],
) -> dict[str, dict[str, float | int]]:
    matched = sum(counts)
    result: dict[str, dict[str, float | int]] = {}
    for limit in limits:
        preserved = sum(min(count, limit) for count in counts)
        result[str(limit)] = {
            "preserved_entries": preserved,
            "preserved_entries_pct": 100.0 * preserved / matched if matched else 0.0,
        }
    return result


def summarize_source_episodes(
    logical: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    source_rows: int,
    supplemental_rows: int,
    limits: Sequence[int],
) -> dict[str, object]:
    """Summarize direction-matched creator entries by causal 5m episode."""
    validated_limits = _validated_limits(limits)
    counts = _episode_counts(logical, decisions)
    matched = sum(counts)
    distribution = Counter(counts)
    provenance = Counter(str(value) for value in logical["timestamp_provenance"])
    return {
        "source_rows": source_rows,
        "supplemental_rows": supplemental_rows,
        "logical_positions": len(logical),
        "direction_matched_positions": matched,
        "direction_mismatched_positions": len(logical) - matched,
        "matched_regime_episodes": len(counts),
        "repeated_regime_episodes": sum(count > 1 for count in counts),
        "entries_in_repeated_episodes": sum(count for count in counts if count > 1),
        "maximum_entries_per_episode": max(counts, default=0),
        "entries_per_episode_distribution": {
            str(key): int(distribution[key]) for key in sorted(distribution)
        },
        "timestamp_provenance_counts": dict(sorted(provenance.items())),
        "limit_compatibility": _limit_compatibility(counts, validated_limits),
    }
