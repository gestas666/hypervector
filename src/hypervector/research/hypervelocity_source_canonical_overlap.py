"""Causal overlap audit between source events and canonical regime decisions."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

EVENT_COLUMNS = ("decision_time_utc", "side")
DECISION_COLUMNS = (
    "primary_regime",
    "entry_direction",
    "state_1m",
    "state_5m",
    "context_15m",
    "confidence",
    "reason",
)
CANONICAL_PREFIX = "canonical_"


def _require_columns(
    frame: pd.DataFrame,
    required: Sequence[str],
    frame_name: str,
) -> None:
    missing = set(required).difference(frame.columns)
    if missing:
        raise ValueError(f"{frame_name} missing required columns: {sorted(missing)}")


def _canonical_utc(decisions: pd.DataFrame) -> pd.DataFrame:
    _require_columns(decisions, DECISION_COLUMNS, "canonical decisions")
    if not isinstance(decisions.index, pd.DatetimeIndex):
        raise ValueError("canonical decisions require a DatetimeIndex")
    if decisions.index.tz is None:
        raise ValueError("canonical decision index must be timezone-aware")
    if not decisions.index.is_unique:
        raise ValueError("canonical decision index must be unique")
    canonical = decisions.copy()
    canonical.index = canonical.index.tz_convert("UTC")
    return canonical.sort_index(kind="stable")


def _event_times(events: pd.DataFrame) -> pd.Series:
    _require_columns(events, EVENT_COLUMNS, "source events")
    times = pd.to_datetime(events["decision_time_utc"], utc=True, errors="raise")
    if times.isna().any():
        raise ValueError("source decision_time_utc cannot contain nulls")
    return times


def _entry_onset_times(
    decisions: pd.DataFrame,
    side: str,
) -> pd.DatetimeIndex:
    direction = decisions["entry_direction"].astype("string")
    onset = direction.eq(side) & ~direction.shift(1).eq(side).fillna(False)
    return decisions.index[onset] + pd.Timedelta(minutes=1)


def _nearest_delta_minutes(
    decision_time: pd.Timestamp,
    onset_times: pd.DatetimeIndex,
) -> float:
    deltas = onset_times - decision_time
    absolute_ns = deltas.asi8.__abs__()
    nearest_position = int(absolute_ns.argmin())
    return float(deltas[nearest_position] / pd.Timedelta(minutes=1))


def _onset_deltas(
    aligned: pd.DataFrame,
    decisions: pd.DataFrame,
) -> pd.Series:
    onsets = {
        side: _entry_onset_times(decisions, side)
        for side in aligned["side"].astype(str).unique()
    }
    values: list[float] = []
    for row in aligned.itertuples(index=False):
        side_onsets = onsets[str(row.side)]
        if not row.canonical_row_available or side_onsets.empty:
            values.append(float("nan"))
            continue
        values.append(_nearest_delta_minutes(row.decision_time_utc, side_onsets))
    return pd.Series(values, index=aligned.index, dtype=float)


def _current_run_ages(
    aligned: pd.DataFrame,
    decisions: pd.DataFrame,
) -> pd.Series:
    onsets = {
        side: _entry_onset_times(decisions, side)
        for side in aligned["side"].astype(str).unique()
    }
    values: list[float] = []
    for row in aligned.itertuples(index=False):
        if row.entry_agreement != "same":
            values.append(float("nan"))
            continue
        prior = onsets[str(row.side)]
        prior = prior[prior <= row.decision_time_utc]
        if prior.empty:
            values.append(float("nan"))
            continue
        age = row.decision_time_utc - prior[-1]
        values.append(float(age / pd.Timedelta(minutes=1)))
    return pd.Series(values, index=aligned.index, dtype=float)


def _agreement(aligned: pd.DataFrame) -> pd.Series:
    available = aligned["canonical_row_available"]
    canonical = aligned["canonical_entry_direction"].astype("string")
    source = aligned["side"].astype("string")
    result = pd.Series("missing", index=aligned.index, dtype="string")
    result = result.mask(available & canonical.isna(), "none")
    result = result.mask(available & canonical.eq(source), "same")
    return result.mask(available & canonical.notna() & canonical.ne(source), "opposite")


def align_source_events_to_canonical_decisions(
    events: pd.DataFrame,
    decisions: pd.DataFrame,
) -> pd.DataFrame:
    """Align source wall-clock events to the last completed canonical 1m bar."""
    canonical = _canonical_utc(decisions)
    aligned = events.copy().reset_index(drop=True)
    aligned["decision_time_utc"] = _event_times(aligned)
    aligned["canonical_bar_time_utc"] = aligned["decision_time_utc"] - pd.Timedelta(
        minutes=1
    )
    bar_times = pd.DatetimeIndex(aligned["canonical_bar_time_utc"])
    aligned["canonical_row_available"] = bar_times.isin(canonical.index)
    selected = canonical.reindex(bar_times).reset_index(drop=True)
    selected = selected.rename(
        columns={column: f"{CANONICAL_PREFIX}{column}" for column in DECISION_COLUMNS}
    )
    aligned = pd.concat([aligned, selected], axis=1)
    aligned["entry_agreement"] = _agreement(aligned)
    aligned["nearest_same_side_onset_delta_minutes"] = _onset_deltas(aligned, canonical)
    aligned["canonical_same_side_run_age_minutes"] = _current_run_ages(
        aligned, canonical
    )
    return aligned


def _value_counts(series: pd.Series) -> dict[str, int]:
    counts = series.dropna().astype(str).value_counts(sort=False)
    return {str(key): int(value) for key, value in sorted(counts.items())}


def summarize_source_canonical_overlap(aligned: pd.DataFrame) -> dict[str, object]:
    """Summarize causal entry agreement and nearest same-side onset timing."""
    _require_columns(
        aligned,
        (
            "canonical_row_available",
            "entry_agreement",
            "nearest_same_side_onset_delta_minutes",
            "canonical_same_side_run_age_minutes",
            "canonical_primary_regime",
        ),
        "aligned overlap",
    )
    available = aligned["canonical_row_available"].astype(bool)
    agreements = aligned["entry_agreement"].astype("string")
    deltas = pd.to_numeric(
        aligned["nearest_same_side_onset_delta_minutes"], errors="raise"
    )
    ages = pd.to_numeric(aligned["canonical_same_side_run_age_minutes"], errors="raise")
    available_count = int(available.sum())
    same_count = int(agreements.eq("same").sum())
    return {
        "events_total": int(len(aligned)),
        "canonical_rows_available": available_count,
        "same_direction_entries": same_count,
        "opposite_direction_entries": int(agreements.eq("opposite").sum()),
        "no_canonical_entry": int(agreements.eq("none").sum()),
        "missing_canonical_rows": int(agreements.eq("missing").sum()),
        "same_direction_entry_rate_available": (
            same_count / available_count if available_count else None
        ),
        "same_side_onset_within_5m": int(deltas.abs().le(5.0).sum()),
        "same_side_onset_within_15m": int(deltas.abs().le(15.0).sum()),
        "same_side_onset_within_30m": int(deltas.abs().le(30.0).sum()),
        "same_side_onset_within_60m": int(deltas.abs().le(60.0).sum()),
        "same_side_current_run_age_within_5m": int(ages.le(5.0).sum()),
        "same_side_current_run_age_within_15m": int(ages.le(15.0).sum()),
        "same_side_current_run_age_within_30m": int(ages.le(30.0).sum()),
        "same_side_current_run_age_within_60m": int(ages.le(60.0).sum()),
        "same_side_current_run_age_median": (
            float(ages.median()) if ages.notna().any() else None
        ),
        "same_side_current_run_age_p90": (
            float(ages.quantile(0.90)) if ages.notna().any() else None
        ),
        "canonical_primary_regime_counts": _value_counts(
            aligned.loc[available, "canonical_primary_regime"]
        ),
    }
