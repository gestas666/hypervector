"""Research-only comparison for an opposite-5m-structure position exit."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from hypervector.research.hypervelocity_margin_stop_compare import (
    summarize_margin_stop_grid,
)
from hypervector.research.hypervelocity_reentry_compare import (
    logical_source_positions,
)
from hypervector.research.maker_replay_models import (
    MakerReplayConfig,
    MakerReplayReport,
)

CONTROL_CANDIDATE = "tp_only_control"
EXIT_CANDIDATE = "opposite_5m_structural_exit"
_CANDIDATES = (CONTROL_CANDIDATE, EXIT_CANDIDATE)


def _replay_config(opposite_regime_exit: bool) -> MakerReplayConfig:
    return MakerReplayConfig(
        initial_equity=10_000.0,
        maker_fee_rate=0.00015,
        taker_fee_rate=0.00045,
        fill_rule="trade-through",
        entry_ttl_seconds=300.0,
        reentry_cooldown_seconds=300.0,
        same_direction_reentry_policy="regime_reset",
        opposite_regime_exit=opposite_regime_exit,
    )


def opposite_regime_exit_candidate_configs() -> dict[str, MakerReplayConfig]:
    """Return the frozen TP-only and opposite-structure replay configs."""
    return {
        CONTROL_CANDIDATE: _replay_config(False),
        EXIT_CANDIDATE: _replay_config(True),
    }


def summarize_opposite_regime_exit(
    reports: Mapping[str, MakerReplayReport],
    configs: Mapping[str, MakerReplayConfig],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    segment_days: int = 30,
) -> dict[str, object]:
    """Summarize the exact two-candidate comparison and path substitutions."""
    if tuple(configs) != _CANDIDATES or set(reports) != set(_CANDIDATES):
        raise ValueError(f"regime-exit candidates must be exactly {_CANDIDATES}")
    summary = summarize_margin_stop_grid(
        reports,
        configs,
        start=start,
        end=end,
        segment_days=segment_days,
    )
    candidates = summary["candidates"]
    if not isinstance(candidates, dict):
        raise RuntimeError("regime-exit summary candidates are invalid")
    for name, config in configs.items():
        candidate = candidates[name]
        if not isinstance(candidate, dict):
            raise RuntimeError(f"regime-exit summary is invalid for {name}")
        candidate["opposite_regime_exit"] = config.opposite_regime_exit
    return summary


def _available(decisions: pd.DataFrame, column: str) -> pd.Series:
    if column not in decisions:
        raise ValueError(f"source exit decisions require {column}")
    if not isinstance(decisions.index, pd.DatetimeIndex):
        raise ValueError("source exit decisions require a DatetimeIndex")
    if decisions.index.tz is None:
        raise ValueError("source exit decisions must be timezone-aware")
    if not decisions.index.is_unique or not decisions.index.is_monotonic_increasing:
        raise ValueError("source exit decisions must be unique and chronological")
    values = decisions[column].astype(object).copy()
    values.index = values.index + pd.Timedelta(minutes=1)
    return values


def _first_match(
    values: pd.Series,
    start: pd.Timestamp,
    end: pd.Timestamp,
    expected: object,
) -> pd.Timestamp | None:
    prior = int(values.index.searchsorted(start, side="right")) - 1
    if prior >= 0 and values.iloc[prior] == expected:
        return start
    window = values.loc[(values.index > start) & (values.index <= end)]
    matches = window.loc[window.eq(expected)]
    return None if matches.empty else pd.Timestamp(matches.index[0])


def _compatibility_row(
    row: pd.Series,
    structural: pd.Series,
    states: pd.Series,
) -> dict[str, object]:
    start = pd.Timestamp(row["open_ts"])
    close_value = row["close_ts"]
    closed = pd.notna(close_value)
    end = pd.Timestamp(close_value) if closed else pd.Timestamp(structural.index[-1])
    opposite = "short" if row["side"] == "long" else "long"
    first_opposite = _first_match(structural, start, end, opposite)
    first_range = _first_match(states, start, end, "RANGE")
    delta = (
        (first_opposite - pd.Timestamp(close_value)).total_seconds()
        if first_opposite is not None and closed
        else None
    )
    return {
        "open_time_utc": start.isoformat(),
        "creator_close_time_utc": (
            pd.Timestamp(close_value).isoformat() if closed else None
        ),
        "side": str(row["side"]),
        "first_opposite_available_utc": (
            first_opposite.isoformat() if first_opposite is not None else None
        ),
        "candidate_minus_creator_close_seconds": delta,
        "range_observed_while_open": first_range is not None,
        "timestamp_provenance": str(row["timestamp_provenance"]),
    }


def source_regime_exit_compatibility(
    positions: pd.DataFrame,
    decisions: pd.DataFrame,
) -> dict[str, object]:
    """Compare causal opposite-5m availability with creator position holds."""
    logical = logical_source_positions(positions)
    structural = _available(decisions, "structural_direction")
    states = _available(decisions, "state_5m")
    rows = [
        _compatibility_row(row, structural, states) for _, row in logical.iterrows()
    ]
    return {
        "logical_positions": len(rows),
        "closed_positions": int(logical["close_ts"].notna().sum()),
        "opposite_structure_while_open": sum(
            row["first_opposite_available_utc"] is not None for row in rows
        ),
        "range_observed_while_open": sum(
            bool(row["range_observed_while_open"]) for row in rows
        ),
        "positions": rows,
    }
