"""Causal report-only interpretations of creator BTC selective recipes."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.regime.models import BreakoutDirection, PrimaryRegime
from hypervector.research.maker_replay_models import MakerReplayConfig

SELECTIVE_RECIPE_CANDIDATES: tuple[str, ...] = (
    "b_confirmed_5m_breakout_up_onset",
    "b_raw_1m_breakout_up_onset_in_5m_long",
    "b_1m_trend_up_onset_in_5m_long",
    "c_5m_trend_down_onset",
    "c_1m_trend_up_recovery_in_5m_down",
)
SELECTIVE_REPLAY_CANDIDATES: tuple[str, ...] = (
    "b_trend_up_onset_all",
    "b_trend_up_onset_current_conf06",
    "c_trend_down_onset",
    "c_1m_recovery_in_5m_down",
    "combined_b_conf06_c",
)

_B_RECIPE = "bk_up_asia_conf06"
_C_RECIPE = "fade_td_eu"
_RECIPE_BY_CANDIDATE: Mapping[str, str] = {
    candidate: _B_RECIPE if candidate.startswith("b_") else _C_RECIPE
    for candidate in SELECTIVE_RECIPE_CANDIDATES
}
_DECISION_COLUMNS = {
    "primary_regime",
    "breakout_direction",
    "state_1m",
    "state_5m",
    "structural_direction",
    "confidence",
}
_RAW_COLUMNS = {"primary_regime", "breakout_direction"}
_SOURCE_COLUMNS = {
    "source_id",
    "recipe_id",
    "side",
    "entry_time_utc_inferred",
}
_EVENT_COLUMNS = {
    "candidate_id",
    "recipe_id",
    "side",
    "event_time_utc",
    "current_confidence",
    "passes_current_confidence_06",
}
_MAKER_TTL = pd.Timedelta(minutes=5)


def _read_bars(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"selective-recipe bars are missing: {path}")
    frame = pd.read_parquet(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"selective-recipe bars missing: {sorted(missing)}")
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
    return frame.loc[:, sorted(required.difference({"timestamp"}))]


def load_selective_recipe_bars(*paths: Path) -> pd.DataFrame:
    """Load immutable candle files into one exact causal 1m history."""
    if not paths:
        raise ValueError("selective-recipe bars require at least one file")
    merged = pd.concat([_read_bars(path) for path in paths]).sort_index(kind="stable")
    if merged.empty or not merged.index.is_unique:
        raise ValueError("selective-recipe bars must be non-empty and nonoverlapping")
    cadence = merged.index.to_series().diff().iloc[1:]
    if not cadence.eq(pd.Timedelta(minutes=1)).all():
        raise ValueError("selective-recipe bars require uninterrupted 1m cadence")
    return merged


def _validate_index(frame: pd.DataFrame, label: str) -> None:
    index = frame.index
    if not isinstance(index, pd.DatetimeIndex):
        raise ValueError(f"{label} require a DatetimeIndex")
    if index.tz is None:
        raise ValueError(f"{label} index must be timezone-aware")
    if not index.is_monotonic_increasing or not index.is_unique:
        raise ValueError(f"{label} index must be ordered and unique")
    if len(index) > 1:
        cadence = index.to_series().diff().iloc[1:]
        if not cadence.eq(pd.Timedelta(minutes=1)).all():
            raise ValueError(f"{label} require uninterrupted one-minute cadence")


def _validate_event_inputs(
    decisions: pd.DataFrame,
    raw_1m: pd.DataFrame,
) -> None:
    _validate_index(decisions, "selective-recipe decisions")
    _validate_index(raw_1m, "selective-recipe raw 1m states")
    if not decisions.index.equals(raw_1m.index):
        raise ValueError(
            "selective-recipe decisions and raw 1m states must share the same index"
        )
    missing_decisions = _DECISION_COLUMNS.difference(decisions.columns)
    missing_raw = _RAW_COLUMNS.difference(raw_1m.columns)
    if missing_decisions:
        raise ValueError(
            f"selective-recipe decisions missing: {sorted(missing_decisions)}"
        )
    if missing_raw:
        raise ValueError(
            f"selective-recipe raw 1m states missing: {sorted(missing_raw)}"
        )


def _onset(active: pd.Series) -> pd.Series:
    values = active.fillna(False).astype(bool)
    if values.empty:
        return values
    prior = values.shift(1, fill_value=bool(values.iloc[0]))
    return values & ~prior


def _session_mask(event_times: pd.DatetimeIndex, recipe_id: str) -> pd.Series:
    utc = event_times.tz_convert("UTC")
    hours = pd.Series(utc.hour, index=event_times)
    if recipe_id == _B_RECIPE:
        return hours.ge(0) & hours.lt(8)
    return hours.ge(7) & hours.lt(16)


def _candidate_conditions(
    decisions: pd.DataFrame,
    raw_1m: pd.DataFrame,
) -> Mapping[str, pd.Series]:
    upward = BreakoutDirection.UPWARD.value
    breakout = PrimaryRegime.BREAKOUT.value
    trend_up = PrimaryRegime.TREND_UP.value
    trend_down = PrimaryRegime.TREND_DOWN.value
    five_minute_long = decisions["structural_direction"].eq("long")
    five_minute_down = decisions["state_5m"].eq(trend_down)
    return {
        SELECTIVE_RECIPE_CANDIDATES[0]: _onset(
            decisions["primary_regime"].eq(breakout)
            & decisions["breakout_direction"].eq(upward)
        ),
        SELECTIVE_RECIPE_CANDIDATES[1]: _onset(
            raw_1m["primary_regime"].eq(breakout)
            & raw_1m["breakout_direction"].eq(upward)
            & five_minute_long
        ),
        SELECTIVE_RECIPE_CANDIDATES[2]: _onset(
            decisions["state_1m"].eq(trend_up) & five_minute_long
        ),
        SELECTIVE_RECIPE_CANDIDATES[3]: _onset(five_minute_down),
        SELECTIVE_RECIPE_CANDIDATES[4]: _onset(
            decisions["state_1m"].eq(trend_up) & five_minute_down
        ),
    }


def _event_rows(
    candidate_id: str,
    active: pd.Series,
    decisions: pd.DataFrame,
) -> pd.DataFrame:
    recipe_id = _RECIPE_BY_CANDIDATE[candidate_id]
    event_times = decisions.index + pd.Timedelta(minutes=1)
    session = _session_mask(event_times, recipe_id).to_numpy(dtype=bool)
    selected = active.to_numpy(dtype=bool) & session
    confidence = pd.to_numeric(decisions["confidence"], errors="raise")
    return pd.DataFrame(
        {
            "candidate_id": candidate_id,
            "recipe_id": recipe_id,
            "side": "long",
            "event_time_utc": event_times[selected].tz_convert("UTC"),
            "current_confidence": confidence.to_numpy(dtype=float)[selected],
        }
    ).assign(
        passes_current_confidence_06=lambda frame: frame["current_confidence"].ge(0.6)
    )


def build_selective_recipe_events(
    decisions: pd.DataFrame,
    raw_1m: pd.DataFrame,
) -> pd.DataFrame:
    """Build the exact finite causal event interpretations for Recipes B/C."""
    _validate_event_inputs(decisions, raw_1m)
    rows = [
        _event_rows(candidate, active, decisions)
        for candidate, active in _candidate_conditions(decisions, raw_1m).items()
    ]
    return pd.concat(rows, ignore_index=True)


def _parsed_sources(source_entries: pd.DataFrame) -> pd.DataFrame:
    missing = _SOURCE_COLUMNS.difference(source_entries.columns)
    if missing:
        raise ValueError(f"selective-recipe source rows missing: {sorted(missing)}")
    parsed = source_entries.loc[:, sorted(_SOURCE_COLUMNS)].copy()
    if parsed.empty:
        raise ValueError("selective-recipe source rows must not be empty")
    if parsed["source_id"].isna().any() or not parsed["source_id"].is_unique:
        raise ValueError("selective-recipe source_id values must be present and unique")
    if not parsed["recipe_id"].isin((_B_RECIPE, _C_RECIPE)).all():
        raise ValueError("selective-recipe source recipe_id is unsupported")
    if not parsed["side"].eq("long").all():
        raise ValueError("selective-recipe source side must be long")
    timestamps = pd.DatetimeIndex(pd.to_datetime(parsed["entry_time_utc_inferred"]))
    if timestamps.tz is None:
        raise ValueError("selective-recipe source timestamps must be timezone-aware")
    timestamps = timestamps.tz_convert("UTC")
    if not timestamps.is_monotonic_increasing:
        raise ValueError("selective-recipe source timestamps must be ordered")
    parsed["entry_time_utc_inferred"] = timestamps
    return parsed


def _validate_events(events: pd.DataFrame) -> None:
    missing = _EVENT_COLUMNS.difference(events.columns)
    if missing:
        raise ValueError(f"selective-recipe events missing: {sorted(missing)}")
    if not events["candidate_id"].isin(SELECTIVE_RECIPE_CANDIDATES).all():
        raise ValueError("selective-recipe events contain an unknown candidate")
    timestamps = pd.DatetimeIndex(pd.to_datetime(events["event_time_utc"]))
    if timestamps.tz is None:
        raise ValueError("selective-recipe event timestamps must be timezone-aware")


def _alignment_row(
    source: pd.Series,
    candidate_id: str,
    candidate_events: pd.DataFrame,
) -> dict[str, object]:
    entry_time = pd.Timestamp(source["entry_time_utc_inferred"])
    prior = candidate_events.loc[candidate_events["event_time_utc"].le(entry_time)]
    causal = None if prior.empty else prior.iloc[-1]
    if candidate_events.empty:
        nearest = None
    else:
        offsets = candidate_events["event_time_utc"] - entry_time
        nearest = candidate_events.iloc[int(np.argmin(offsets.abs().to_numpy()))]
    lag = None if causal is None else entry_time - causal["event_time_utc"]
    matched = lag is not None and lag <= _MAKER_TTL
    nearest_offset = None if nearest is None else nearest["event_time_utc"] - entry_time
    return {
        "source_id": str(source["source_id"]),
        "recipe_id": str(source["recipe_id"]),
        "candidate_id": candidate_id,
        "entry_time_utc": entry_time,
        "causal_event_time_utc": None if causal is None else causal["event_time_utc"],
        "causal_lag_seconds": None if lag is None else lag.total_seconds(),
        "matched_within_maker_ttl": matched,
        "matched_within_maker_ttl_conf06": matched
        and bool(causal["passes_current_confidence_06"]),
        "nearest_event_time_utc": None
        if nearest is None
        else nearest["event_time_utc"],
        "nearest_offset_seconds": (
            None if nearest_offset is None else nearest_offset.total_seconds()
        ),
        "nearest_is_future": nearest_offset is not None
        and nearest_offset > pd.Timedelta(0),
    }


def align_creator_recipe_entries(
    source_entries: pd.DataFrame,
    events: pd.DataFrame,
) -> pd.DataFrame:
    """Align creator rows to causal prior events and noncausal nearest sensitivity."""
    source = _parsed_sources(source_entries)
    _validate_events(events)
    rows: list[dict[str, object]] = []
    for candidate_id in SELECTIVE_RECIPE_CANDIDATES:
        recipe_id = _RECIPE_BY_CANDIDATE[candidate_id]
        candidate_events = events.loc[
            events["candidate_id"].eq(candidate_id)
        ].sort_values("event_time_utc", kind="stable")
        recipe_sources = source.loc[source["recipe_id"].eq(recipe_id)]
        rows.extend(
            _alignment_row(entry, candidate_id, candidate_events)
            for _, entry in recipe_sources.iterrows()
        )
    return pd.DataFrame(rows)


def summarize_selective_recipe_alignment(
    source_entries: pd.DataFrame,
    events: pd.DataFrame,
    alignment: pd.DataFrame,
) -> dict[str, dict[str, object]]:
    """Summarize positive coverage and cadence without claiming precision."""
    source = _parsed_sources(source_entries)
    _validate_events(events)
    summaries: dict[str, dict[str, object]] = {}
    for candidate_id in SELECTIVE_RECIPE_CANDIDATES:
        recipe_id = _RECIPE_BY_CANDIDATE[candidate_id]
        candidate_events = events.loc[events["candidate_id"].eq(candidate_id)]
        candidate_rows = alignment.loc[alignment["candidate_id"].eq(candidate_id)]
        source_rows = int(source["recipe_id"].eq(recipe_id).sum())
        matched = int(candidate_rows["matched_within_maker_ttl"].sum())
        matched_times = set(
            candidate_rows.loc[
                candidate_rows["matched_within_maker_ttl"], "causal_event_time_utc"
            ].dropna()
        )
        total_events = len(candidate_events)
        summaries[candidate_id] = {
            "recipe_id": recipe_id,
            "source_rows": source_rows,
            "matched_within_maker_ttl": matched,
            "matched_within_maker_ttl_conf06": int(
                candidate_rows["matched_within_maker_ttl_conf06"].sum()
            ),
            "source_coverage_pct": 100.0 * matched / source_rows,
            "total_candidate_events": total_events,
            "unobserved_event_count": total_events - len(matched_times),
            "precision_estimable": False,
        }
    return summaries


def _replay_config(initial_equity: float) -> MakerReplayConfig:
    return MakerReplayConfig(
        initial_equity=initial_equity,
        maker_fee_rate=0.00015,
        taker_fee_rate=0.00045,
        fill_rule="trade-through",
        entry_ttl_seconds=300.0,
        reentry_cooldown_seconds=60.0,
        same_direction_reentry_policy="regime_reset",
    )


def _replay_event_sets(events: pd.DataFrame) -> dict[str, pd.DataFrame]:
    b = events.loc[events["candidate_id"].eq("b_1m_trend_up_onset_in_5m_long")].copy()
    b["maximum_hold_seconds"] = 14_400.0
    b_confident = b.loc[b["passes_current_confidence_06"]].copy()
    c = events.loc[events["candidate_id"].eq("c_5m_trend_down_onset")].copy()
    c["maximum_hold_seconds"] = 86_400.0
    recovery = events.loc[
        events["candidate_id"].eq("c_1m_trend_up_recovery_in_5m_down")
    ].copy()
    recovery["maximum_hold_seconds"] = 86_400.0
    combined = pd.concat([b_confident, c], ignore_index=True).sort_values(
        "event_time_utc", kind="stable"
    )
    return dict(
        zip(
            SELECTIVE_REPLAY_CANDIDATES,
            (b, b_confident, c, recovery, combined),
            strict=True,
        )
    )


def _decision_frame(
    base_decisions: pd.DataFrame,
    selected_events: pd.DataFrame,
) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "entry_direction": None,
            "structural_direction": None,
            "maximum_hold_seconds": None,
        },
        index=base_decisions.index,
        dtype=object,
    )
    for _, event in selected_events.iterrows():
        signal_bar = pd.Timestamp(event["event_time_utc"]) - pd.Timedelta(minutes=1)
        if signal_bar not in frame.index:
            raise ValueError(
                f"selective-recipe event is outside decisions: {signal_bar}"
            )
        maximum = float(event["maximum_hold_seconds"])
        existing = frame.at[signal_bar, "maximum_hold_seconds"]
        if existing is not None and float(existing) != maximum:
            raise ValueError(f"conflicting recipe deadlines at {signal_bar}")
        frame.at[signal_bar, "entry_direction"] = "long"
        frame.at[signal_bar, "maximum_hold_seconds"] = maximum
        keepalive_end = signal_bar + pd.Timedelta(minutes=5)
        frame.loc[signal_bar:keepalive_end, "structural_direction"] = "long"
    return frame


def selective_recipe_replay_inputs(
    base_decisions: pd.DataFrame,
    events: pd.DataFrame,
    *,
    initial_equity: float = 10_000.0,
) -> tuple[dict[str, pd.DataFrame], dict[str, MakerReplayConfig]]:
    """Build exact report-only decision/config grids for B/C proxy replay."""
    _validate_index(base_decisions, "selective-recipe replay decisions")
    _validate_events(events)
    event_sets = _replay_event_sets(events)
    decisions = {
        name: _decision_frame(base_decisions, selected)
        for name, selected in event_sets.items()
    }
    configs = {
        name: _replay_config(initial_equity) for name in SELECTIVE_REPLAY_CANDIDATES
    }
    return decisions, configs
