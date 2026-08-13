"""Causal source-regime projections for report-only exit research."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hypertrader_source_adapter import (
    selective_recipe_maker_decisions,
)

_LABEL_COLUMNS = {"primary_code", "secondary_code"}
_FLAT = "flat"


def _source_structure(labels: pd.DataFrame) -> pd.Series:
    if not isinstance(labels.index, pd.DatetimeIndex) or labels.index.tz is None:
        raise ValueError("source labels require a timezone-aware DatetimeIndex")
    if not labels.index.is_monotonic_increasing or not labels.index.is_unique:
        raise ValueError("source label timestamps must be ordered and unique")
    missing = _LABEL_COLUMNS.difference(labels.columns)
    if missing:
        raise ValueError(f"source labels missing: {sorted(missing)}")
    primary = labels["primary_code"].fillna("UNKNOWN").astype(str).str.upper()
    secondary = labels["secondary_code"].fillna("").astype(str).str.upper()
    direction = pd.Series(_FLAT, index=labels.index, dtype=object)
    direction.loc[primary.eq("TREND_UP")] = "long"
    direction.loc[primary.eq("TREND_DOWN")] = "short"
    breakout = primary.eq("BREAKOUT")
    direction.loc[breakout & secondary.eq("BK_UPWARD")] = "long"
    direction.loc[breakout & secondary.eq("BK_DOWNWARD")] = "short"
    direction.index = direction.index + pd.Timedelta(minutes=4)
    return direction


def selective_recipe_source_exit_decisions(
    events: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    entry_eligibility_seconds: float = 300.0,
) -> pd.DataFrame:
    """Combine onset entry pulses with continuously published source structure."""
    pulses = selective_recipe_maker_decisions(
        events,
        entry_eligibility_seconds=entry_eligibility_seconds,
    )
    updates = _source_structure(labels)
    index = pulses.index.union(updates.index).sort_values()
    result = pulses.reindex(index)
    states = updates.reindex(index).ffill().fillna(_FLAT)
    result["structural_direction"] = states.mask(states.eq(_FLAT), None)
    return result
