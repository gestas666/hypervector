"""Transparent report-only ranking of continuous research opportunities."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

Record = Mapping[str, object]


@dataclass(frozen=True)
class _ExperimentSpec:
    information_class: int
    information_value: str
    complexity_class: int
    complexity: str
    downside_class: int
    downside: str


_SPECS = {
    "collect_both_side_forward_paths": _ExperimentSpec(
        4,
        "high",
        0,
        "none_for_observation",
        2,
        "modeled_paths_can_diverge_from_executable_fills",
    ),
    "collect_and_resolve_source_transport_parity": _ExperimentSpec(
        5,
        "very_high",
        1,
        "low_report_only",
        3,
        "source_mismatch_can_invalidate_economics",
    ),
    "diagnose_long_entry_quality": _ExperimentSpec(
        5,
        "very_high",
        1,
        "low_report_only",
        3,
        "post_hoc_small_sample_and_threshold_overfit_risk",
    ),
    "collect_both_side_live_execution": _ExperimentSpec(
        4, "high", 0, "none_for_observation", 2, "sparse_evidence_can_mislead"
    ),
    "collect_route_native_one_blocker_shadow": _ExperimentSpec(
        4,
        "high",
        1,
        "low_report_only",
        2,
        "small_one_blocker_samples_can_mislead",
    ),
    "collect_route_specific_regime_context_evidence": _ExperimentSpec(
        4,
        "high",
        0,
        "none_for_observation",
        2,
        "sparse_context_cohorts_can_mislead",
    ),
    "collect_side_specific_evidence": _ExperimentSpec(
        4, "high", 0, "none_for_observation", 2, "sparse_evidence_can_mislead"
    ),
    "shared_portfolio_interaction_replay": _ExperimentSpec(
        4, "high", 2, "medium_report_only", 2, "model_assumptions_can_mislead"
    ),
    "separate_long_short_mechanisms": _ExperimentSpec(
        3, "medium", 2, "medium_report_only", 3, "post_hoc_side_selection_risk"
    ),
    "diagnose_signal_cost_or_concentration": _ExperimentSpec(
        3, "medium", 1, "low_report_only", 2, "small_samples_can_hide_concentration"
    ),
    "establish_source_backed_mechanism": _ExperimentSpec(
        2, "exploratory", 3, "high_research", 4, "multiple_testing_and_overfit_risk"
    ),
    "new_side_mechanic_version_required": _ExperimentSpec(
        2, "exploratory", 3, "high_research", 4, "multiple_testing_and_overfit_risk"
    ),
    "new_mechanic_version_required": _ExperimentSpec(
        2, "exploratory", 3, "high_research", 4, "multiple_testing_and_overfit_risk"
    ),
}
_CONFIDENCE = {"low": 1, "low_to_medium": 1, "medium": 2, "high": 3}


def rank_research_opportunities(
    queue: Sequence[Record],
    scores: Record,
) -> list[dict[str, object]]:
    """Rank investigations by information value with explicit uncertainty."""
    rows = [_rank_input(row, scores) for row in queue]
    rows.sort(key=_sort_key)
    return [dict(row, validation_priority=index) for index, row in enumerate(rows, 1)]


def _rank_input(row: Record, scores: Record) -> dict[str, object]:
    route = _text(row.get("route"), "opportunity route")
    experiment = _text(row.get("next_experiment"), "opportunity experiment")
    if experiment not in _SPECS:
        raise ValueError(f"unsupported opportunity experiment: {experiment}")
    score = _mapping(scores.get(route), f"opportunity score {route}")
    confidence = _text(score.get("confidence"), "opportunity confidence")
    if confidence not in _CONFIDENCE:
        raise ValueError(f"unsupported opportunity confidence: {confidence}")
    spec = _SPECS[experiment]
    original_rank = _nonnegative_int(row.get("research_rank"), "research rank")
    return {
        "route": route,
        "experiment": experiment,
        "expected_economic_value": "unquantified_until_compatible_forward_lifecycles",
        "expected_information_value": spec.information_value,
        "confidence": confidence,
        "implementation_complexity": spec.complexity,
        "downside": spec.downside,
        "rank_basis": {
            "information_value_class": spec.information_class,
            "confidence_class": _CONFIDENCE[confidence],
            "complexity_class": spec.complexity_class,
            "downside_class": spec.downside_class,
            "prior_queue_rank": original_rank,
        },
        "execution_effect": "report_only",
        "automatic_live_change": False,
    }


def _sort_key(row: Record) -> tuple[int, int, int, int, int, str]:
    basis = _mapping(row.get("rank_basis"), "opportunity rank basis")
    return (
        -_nonnegative_int(basis.get("information_value_class"), "information class"),
        _nonnegative_int(basis.get("prior_queue_rank"), "prior rank"),
        -_nonnegative_int(basis.get("confidence_class"), "confidence class"),
        _nonnegative_int(basis.get("complexity_class"), "complexity class"),
        _nonnegative_int(basis.get("downside_class"), "downside class"),
        _text(row.get("route"), "opportunity route"),
    )


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
