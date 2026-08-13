"""Compact immutable reporting for ETH/SOL low-timeframe tuning."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Literal

from hypervector.research.low_tf_asset_tuning_models import (
    DevelopmentTrialSummary,
    LowTfAssetTrial,
    TuningTrialResult,
)

QualificationState = Literal[
    "research_only",
    "forward_observe",
    "canary_candidate",
]

_ENTRY_AXES: tuple[tuple[object, ...], ...] = (
    (24, 48, 120),
    ((9, 21), (13, 34), (21, 55)),
    (20.0, 35.0),
    (4.0, 8.0),
)
_EXIT_AXES: tuple[tuple[object, ...], ...] = (
    (40.0, 80.0),
    (1.5, 2.0, 3.0),
    (12, 24),
)


def development_neighbor_sensitivity(
    trial: LowTfAssetTrial,
    trials: tuple[LowTfAssetTrial, ...],
    results: tuple[TuningTrialResult, ...],
) -> dict[str, int | float]:
    """Report direct-neighbor support without deleting brittle optima."""
    indexed = {result.trial_id: result for result in results}
    neighbors = tuple(
        candidate
        for candidate in trials
        if candidate.symbol == trial.symbol
        and candidate.side == trial.side
        and _direct_neighbor(trial, candidate)
    )
    missing = [
        candidate.trial_id
        for candidate in neighbors
        if candidate.trial_id not in indexed
    ]
    if missing:
        raise ValueError(f"neighbor results are incomplete: {missing[:3]}")
    positive = sum(
        indexed[candidate.trial_id].net_pnl_usd > 0.0
        and indexed[candidate.trial_id].liquidations == 0
        for candidate in neighbors
    )
    count = len(neighbors)
    return {
        "evaluated_neighbors": count,
        "positive_neighbors": positive,
        "positive_neighbor_fraction": positive / count if count else 0.0,
    }


def build_tuning_artifact(
    *,
    run_id: str,
    source_identity: dict[str, object],
    trials: tuple[LowTfAssetTrial, ...],
    development_results: tuple[TuningTrialResult, ...],
    development_summaries: tuple[DevelopmentTrialSummary, ...],
    selected_trials: tuple[LowTfAssetTrial, ...],
    replay_results: tuple[TuningTrialResult, ...],
) -> dict[str, object]:
    """Build a compact report-only artifact retaining the complete search."""
    _validate_artifact_inputs(
        run_id,
        source_identity,
        trials,
        development_results,
        development_summaries,
        selected_trials,
        replay_results,
    )
    qualification = [
        _qualification_row(trial, trials, development_results, replay_results)
        for trial in selected_trials
    ]
    return {
        "schema_version": 1,
        "run_id": run_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "qualification_is_descriptive_only": True,
        "source_identity": source_identity,
        "declared_trial_count": len(trials),
        "retained_development_result_count": len(development_results),
        "selected_trial_ids": [trial.trial_id for trial in selected_trials],
        "development_summaries": [asdict(value) for value in development_summaries],
        "development_results": [
            _compact_result(value) for value in development_results
        ],
        "replay_results": [_compact_result(value) for value in replay_results],
        "qualification": qualification,
        "limitations": [
            "pseudo_holdout was inspected by earlier research and is not pristine",
            "bar and minute replay cannot reproduce queue position or transient depth",
            "qualification labels grant no execution authority",
        ],
    }


def _compact_result(result: TuningTrialResult) -> dict[str, object]:
    """Return metrics only; complete trade rows live in DuckDB."""
    values = asdict(result)
    values.pop("trade_records")
    return values


def _qualification_row(
    trial: LowTfAssetTrial,
    trials: tuple[LowTfAssetTrial, ...],
    development: tuple[TuningTrialResult, ...],
    replay: tuple[TuningTrialResult, ...],
) -> dict[str, object]:
    sensitivity = development_neighbor_sensitivity(trial, trials, development)
    selected = tuple(result for result in replay if result.trial_id == trial.trial_id)
    state, reasons = _qualification_state(selected, sensitivity)
    return {
        "trial_id": trial.trial_id,
        "symbol": trial.symbol,
        "side": trial.side,
        "state": state,
        "reasons": reasons,
        "development_neighbor_sensitivity": sensitivity,
    }


def _qualification_state(
    results: tuple[TuningTrialResult, ...],
    sensitivity: dict[str, int | float],
) -> tuple[QualificationState, list[str]]:
    required = {
        (segment, scenario)
        for segment in ("development", "validation", "pseudo_holdout")
        for scenario in ("nominal", "stress")
    }
    indexed = {(result.segment, result.scenario): result for result in results}
    if set(indexed) != required:
        return "research_only", ["chronological minute-replay matrix incomplete"]
    later = tuple(
        result
        for result in results
        if result.segment in {"validation", "pseudo_holdout"}
    )
    if any(result.liquidations for result in results):
        return "research_only", ["one or more replay liquidations"]
    if any(result.net_pnl_usd <= 0.0 for result in later):
        return "research_only", ["later-window nominal or stress net is non-positive"]
    later_trades = sum(
        result.completed_trades for result in later if result.scenario == "nominal"
    )
    fraction = float(sensitivity["positive_neighbor_fraction"])
    if later_trades >= 20 and fraction >= 0.5:
        return "canary_candidate", [
            "later windows and local development neighborhood supported"
        ]
    return "forward_observe", [
        "later windows positive but evidence density or neighbors remain limited"
    ]


def _direct_neighbor(left: LowTfAssetTrial, right: LowTfAssetTrial) -> bool:
    left_values = (
        left.entry.breakout_lookback,
        (left.entry.ema_fast, left.entry.ema_slow),
        left.entry.compression_percentile,
        left.entry.clearance_bps,
        left.exit.stop_bps,
        left.exit.target_r_multiple,
        left.exit.maximum_hold_bars,
    )
    right_values = (
        right.entry.breakout_lookback,
        (right.entry.ema_fast, right.entry.ema_slow),
        right.entry.compression_percentile,
        right.entry.clearance_bps,
        right.exit.stop_bps,
        right.exit.target_r_multiple,
        right.exit.maximum_hold_bars,
    )
    return _adjacent_on_one_axis(left_values, right_values, (*_ENTRY_AXES, *_EXIT_AXES))


def _adjacent_on_one_axis(
    left: tuple[object, ...],
    right: tuple[object, ...],
    axes: tuple[tuple[object, ...], ...],
) -> bool:
    changes = 0
    for left_value, right_value, axis in zip(left, right, axes, strict=True):
        if left_value == right_value:
            continue
        if left_value not in axis or right_value not in axis:
            return False
        if abs(axis.index(left_value) - axis.index(right_value)) != 1:
            return False
        changes += 1
    return changes == 1


def _validate_artifact_inputs(
    run_id: str,
    source_identity: dict[str, object],
    trials: tuple[LowTfAssetTrial, ...],
    development: tuple[TuningTrialResult, ...],
    summaries: tuple[DevelopmentTrialSummary, ...],
    selected: tuple[LowTfAssetTrial, ...],
    replay: tuple[TuningTrialResult, ...],
) -> None:
    if not run_id.strip() or not source_identity or not trials:
        raise ValueError("tuning artifact requires run, source, and trial identities")
    trial_ids = {trial.trial_id for trial in trials}
    if len(trial_ids) != len(trials):
        raise ValueError("tuning artifact trials contain duplicate identities")
    if {result.trial_id for result in development} != trial_ids:
        raise ValueError("tuning artifact must retain every development trial")
    if {summary.trial_id for summary in summaries} != trial_ids:
        raise ValueError("tuning artifact summaries must cover every trial")
    selected_ids = {trial.trial_id for trial in selected}
    if not selected_ids.issubset(trial_ids):
        raise ValueError("selected tuning trial was not declared")
    if any(result.trial_id not in selected_ids for result in replay):
        raise ValueError("replay result does not belong to a selected trial")
