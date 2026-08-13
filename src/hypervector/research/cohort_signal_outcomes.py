"""Causal forward-path diagnostics for cohort provider evaluations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from statistics import median

from hypervector.research.cohort_live_audit_values import mapping, nonnegative_int
from hypervector.research.cohort_forward_paths import (
    Candle,
    DirectionalPath,
    build_candle_index,
    non_overlapping_count,
    non_overlapping_paths,
    resolve_directional_path,
    validated_horizons,
)
from hypervector.research.cohort_signal_candidates import (
    SignalCandidate,
    evaluation_candidates,
)
from hypervector.research.cohort_opportunity_capture import (
    DEFAULT_ESTIMATED_ROUND_TRIP_FRICTION_BPS,
    DEFAULT_ROBUST_GROSS_MOVE_BPS,
    OpportunityHurdles,
    opportunity_hurdles,
    summarize_path_opportunities,
)
from hypervector.research.cohort_portfolio_opportunity_dedup import (
    build_portfolio_opportunity_dedup,
)
from hypervector.research.cohort_signal_metric_diagnostics import (
    MetricDiagnosticsAccumulator,
)

Record = Mapping[str, object]
_DEFAULT_HORIZONS = (5, 15, 30, 60)


@dataclass
class _HorizonEvidence:
    outcomes: list[DirectionalPath] = field(default_factory=list)
    censored: int = 0
    missing_data: int = 0


@dataclass
class _ProviderEvidence:
    metric_diagnostics: MetricDiagnosticsAccumulator
    evaluations: int = 0
    eligible_evaluations: int = 0
    readiness_annotations: int = 0
    no_direction: int = 0
    side_evaluations: dict[str, int] = field(
        default_factory=lambda: {"long": 0, "short": 0}
    )
    side_eligible_evaluations: dict[str, int] = field(
        default_factory=lambda: {"long": 0, "short": 0}
    )
    horizons: dict[int, _HorizonEvidence] = field(default_factory=dict)
    eligible_horizons: dict[int, _HorizonEvidence] = field(default_factory=dict)
    readiness_horizons: dict[int, _HorizonEvidence] = field(default_factory=dict)
    blocker_horizons: dict[str, dict[int, _HorizonEvidence]] = field(
        default_factory=dict
    )
    blocker_counts: dict[str, int] = field(default_factory=dict)
    one_blocker_horizons: dict[str, dict[int, _HorizonEvidence]] = field(
        default_factory=dict
    )
    one_blocker_counts: dict[str, int] = field(default_factory=dict)
    one_blocker_side_horizons: dict[tuple[str, str], dict[int, _HorizonEvidence]] = (
        field(default_factory=dict)
    )
    one_blocker_side_counts: dict[tuple[str, str], int] = field(default_factory=dict)


def build_provider_forward_diagnostics(
    records: Sequence[Record],
    *,
    horizons_minutes: Sequence[int] = _DEFAULT_HORIZONS,
    estimated_round_trip_friction_bps: float = (
        DEFAULT_ESTIMATED_ROUND_TRIP_FRICTION_BPS
    ),
    robust_gross_move_bps: float = DEFAULT_ROBUST_GROSS_MOVE_BPS,
) -> dict[str, object]:
    """Measure future candle paths without assuming orders, fills, or PnL."""
    horizons = validated_horizons(horizons_minutes)
    hurdles = opportunity_hurdles(
        estimated_round_trip_friction_bps,
        robust_gross_move_bps,
    )
    candidates, excluded, direction_conflicts = evaluation_candidates(records)
    candles = build_candle_index(records)
    buckets: dict[str, _ProviderEvidence] = {}
    for candidate in candidates:
        key = f"{candidate.strategy_id}|{candidate.symbol}"
        bucket = buckets.setdefault(key, _provider_evidence(horizons))
        _observe_candidate(bucket, candidate, candles.get(candidate.symbol, {}))
    return _build_report(
        candidates,
        excluded,
        direction_conflicts,
        candles,
        buckets,
        horizons,
        hurdles,
    )


def _build_report(
    candidates: Sequence[SignalCandidate],
    excluded: int,
    direction_conflicts: int,
    candles: Mapping[str, Mapping[int, Candle]],
    buckets: Mapping[str, _ProviderEvidence],
    horizons: Sequence[int],
    hurdles: OpportunityHurdles,
) -> dict[str, object]:
    return {
        "contract": {
            "counterfactual_only": True,
            "fills_assumed": False,
            "pnl_claimed": False,
            "execution_authority": "none",
            "model_trained": False,
            "thresholds_selected": False,
        },
        "horizons_minutes": list(horizons),
        "opportunity_hurdles_bps": hurdles.as_payload(),
        "evaluations": len(candidates),
        "eligible_evaluations": sum(value.eligible for value in candidates),
        "directional_evaluations": sum(value.side is not None for value in candidates),
        "direction_conflicts": direction_conflicts,
        "preactivation_annotations_excluded": excluded,
        "coverage": _coverage(buckets, direction_conflicts),
        "portfolio_opportunity_dedup": build_portfolio_opportunity_dedup(
            candidates,
            candles,
            horizons,
            hurdles,
        ),
        "by_provider_symbol": {
            key: _provider_summary(value, hurdles)
            for key, value in sorted(buckets.items())
        },
        "limitations": [
            "overlapping forward paths are descriptive and not independent samples",
            "completed candles do not reveal intrabar order sequence or queue position",
            "diagnostics assume no order, fill, fee, funding, sizing, or realized PnL",
            "metric-conditioned outcomes are descriptive and do not select thresholds",
            "cost hurdles are fixed assumptions, not exact executable fill economics",
        ],
    }


def _coverage(
    buckets: Mapping[str, _ProviderEvidence], direction_conflicts: int
) -> dict[str, object]:
    evidence = [
        item for bucket in buckets.values() for item in bucket.horizons.values()
    ]
    missing = sum(item.missing_data for item in evidence)
    metric_coverages = [
        mapping(
            bucket.metric_diagnostics.as_payload().get("coverage"),
            "provider metric coverage",
        )
        for bucket in buckets.values()
    ]
    metrics_complete = all(value.get("complete") is True for value in metric_coverages)
    return {
        "complete": missing == 0 and metrics_complete and direction_conflicts == 0,
        "market_data_complete": missing == 0,
        "metric_telemetry_complete": metrics_complete,
        "missing_data_observations": missing,
        "right_censored_observations": sum(item.censored for item in evidence),
        "direction_conflicts": direction_conflicts,
        "evaluations_without_metrics": sum(
            nonnegative_int(
                value.get("evaluations_without_metrics"),
                "evaluations without metrics",
            )
            for value in metric_coverages
        ),
        "metric_value_gaps": sum(
            nonnegative_int(value.get("metric_value_gaps"), "metric value gaps")
            for value in metric_coverages
        ),
    }


def _provider_evidence(horizons: Sequence[int]) -> _ProviderEvidence:
    return _ProviderEvidence(
        metric_diagnostics=MetricDiagnosticsAccumulator(horizons),
        horizons=_horizon_evidence(horizons),
        eligible_horizons=_horizon_evidence(horizons),
        readiness_horizons=_horizon_evidence(horizons),
    )


def _horizon_evidence(horizons: Sequence[int]) -> dict[int, _HorizonEvidence]:
    return {value: _HorizonEvidence() for value in horizons}


def _observe_candidate(
    bucket: _ProviderEvidence,
    candidate: SignalCandidate,
    candles: Mapping[int, Candle],
) -> None:
    bucket.evaluations += 1
    bucket.metric_diagnostics.observe_evaluation(candidate.metrics)
    if candidate.eligible:
        bucket.eligible_evaluations += 1
    elif candidate.side is not None:
        bucket.readiness_annotations += 1
    if candidate.side is None:
        bucket.no_direction += 1
        return
    bucket.side_evaluations[candidate.side] += 1
    if candidate.eligible:
        bucket.side_eligible_evaluations[candidate.side] += 1
    class_horizons = (
        bucket.eligible_horizons if candidate.eligible else bucket.readiness_horizons
    )
    for horizon, evidence in bucket.horizons.items():
        status, outcome = _resolve(candidate, candles, horizon)
        bucket.metric_diagnostics.observe_horizon(
            candidate.metrics,
            horizon_minutes=horizon,
            decision_time_ms=candidate.decision_time_ms,
            status=status,
            directional_return_bps=(
                outcome.directional_close_return_bps if outcome is not None else None
            ),
        )
        _record_outcome(evidence, status, outcome)
        _record_outcome(class_horizons[horizon], status, outcome)
        _record_blockers(bucket, candidate, horizon, status, outcome)


def _record_blockers(
    bucket: _ProviderEvidence,
    candidate: SignalCandidate,
    horizon: int,
    status: str,
    outcome: DirectionalPath | None,
) -> None:
    if candidate.eligible:
        return
    for blocker in candidate.blockers:
        if blocker not in bucket.blocker_horizons:
            bucket.blocker_horizons[blocker] = _horizon_evidence(tuple(bucket.horizons))
            bucket.blocker_counts[blocker] = 0
        if horizon == min(bucket.horizons):
            bucket.blocker_counts[blocker] += 1
        _record_outcome(bucket.blocker_horizons[blocker][horizon], status, outcome)
    _record_one_blocker(bucket, candidate, horizon, status, outcome)


def _record_one_blocker(
    bucket: _ProviderEvidence,
    candidate: SignalCandidate,
    horizon: int,
    status: str,
    outcome: DirectionalPath | None,
) -> None:
    if len(candidate.blockers) != 1:
        return
    blocker = candidate.blockers[0]
    if blocker not in bucket.one_blocker_horizons:
        bucket.one_blocker_horizons[blocker] = _horizon_evidence(tuple(bucket.horizons))
        bucket.one_blocker_counts[blocker] = 0
    if horizon == min(bucket.horizons):
        bucket.one_blocker_counts[blocker] += 1
    _record_outcome(bucket.one_blocker_horizons[blocker][horizon], status, outcome)
    if candidate.side is None:
        raise RuntimeError("one-blocker path requires a direction")
    side_key = (blocker, candidate.side)
    if side_key not in bucket.one_blocker_side_horizons:
        bucket.one_blocker_side_horizons[side_key] = _horizon_evidence(
            tuple(bucket.horizons)
        )
        bucket.one_blocker_side_counts[side_key] = 0
    if horizon == min(bucket.horizons):
        bucket.one_blocker_side_counts[side_key] += 1
    _record_outcome(
        bucket.one_blocker_side_horizons[side_key][horizon], status, outcome
    )


def _record_outcome(
    evidence: _HorizonEvidence,
    status: str,
    outcome: DirectionalPath | None,
) -> None:
    if status == "censored":
        evidence.censored += 1
    elif status == "missing_data":
        evidence.missing_data += 1
    elif outcome is not None:
        evidence.outcomes.append(outcome)


def _resolve(
    candidate: SignalCandidate,
    candles: Mapping[int, Candle],
    horizon: int,
) -> tuple[str, DirectionalPath | None]:
    if candidate.side is None:
        raise RuntimeError("directional path resolution requires a side")
    return resolve_directional_path(
        decision_time_ms=candidate.decision_time_ms,
        reference_price=candidate.reference_price,
        side=candidate.side,
        candles=candles,
        horizon_minutes=horizon,
    )


def _provider_summary(
    evidence: _ProviderEvidence,
    hurdles: OpportunityHurdles,
) -> dict[str, object]:
    return {
        "evaluations": evidence.evaluations,
        "eligible_evaluations": evidence.eligible_evaluations,
        "readiness_annotations": evidence.readiness_annotations,
        "no_direction": evidence.no_direction,
        "by_side": _directional_counts(evidence),
        "horizons": {
            str(value): _horizon_summary(item, value, hurdles)
            for value, item in sorted(evidence.horizons.items())
        },
        "by_evidence_class": _evidence_classes(evidence, hurdles),
        "by_blocker": {
            blocker: _evidence_class_summary(
                evidence.blocker_counts[blocker], horizons, hurdles
            )
            for blocker, horizons in sorted(evidence.blocker_horizons.items())
        },
        "one_blocker_near_misses": {
            "evaluations": sum(evidence.one_blocker_counts.values()),
            "by_blocker": {
                blocker: {
                    **_evidence_class_summary(
                        evidence.one_blocker_counts[blocker], horizons, hurdles
                    ),
                    "by_side": {
                        side: _evidence_class_summary(
                            evidence.one_blocker_side_counts[(blocker, side)],
                            evidence.one_blocker_side_horizons[(blocker, side)],
                            hurdles,
                        )
                        for side in ("long", "short")
                        if (blocker, side) in evidence.one_blocker_side_horizons
                    },
                }
                for blocker, horizons in sorted(evidence.one_blocker_horizons.items())
            },
        },
        "metric_diagnostics": evidence.metric_diagnostics.as_payload(),
    }


def _directional_counts(
    evidence: _ProviderEvidence,
) -> dict[str, dict[str, int]]:
    return {
        side: {
            "evaluations": evidence.side_evaluations[side],
            "eligible_evaluations": evidence.side_eligible_evaluations[side],
        }
        for side in ("long", "short")
    }


def _evidence_classes(
    evidence: _ProviderEvidence,
    hurdles: OpportunityHurdles,
) -> dict[str, dict[str, object]]:
    return {
        "eligible_signal": _evidence_class_summary(
            evidence.eligible_evaluations, evidence.eligible_horizons, hurdles
        ),
        "readiness_annotation": _evidence_class_summary(
            evidence.readiness_annotations, evidence.readiness_horizons, hurdles
        ),
    }


def _evidence_class_summary(
    evaluations: int,
    horizons: Mapping[int, _HorizonEvidence],
    hurdles: OpportunityHurdles,
) -> dict[str, object]:
    return {
        "evaluations": evaluations,
        "horizons": {
            str(value): _horizon_summary(item, value, hurdles)
            for value, item in sorted(horizons.items())
        },
    }


def _horizon_summary(
    evidence: _HorizonEvidence,
    horizon_minutes: int,
    hurdles: OpportunityHurdles,
) -> dict[str, object]:
    independent = non_overlapping_paths(evidence.outcomes, horizon_minutes)
    returns = [value.directional_close_return_bps for value in evidence.outcomes]
    favorable = [value.favorable_excursion_bps for value in evidence.outcomes]
    adverse = [value.adverse_excursion_bps for value in evidence.outcomes]
    return {
        "resolved": len(evidence.outcomes),
        "non_overlapping_resolved": _non_overlapping_count(
            evidence.outcomes, horizon_minutes
        ),
        "censored": evidence.censored,
        "missing_data": evidence.missing_data,
        "positive_directional_rate": (
            sum(value > 0.0 for value in returns) / len(returns) if returns else None
        ),
        "mean_directional_close_return_bps": _mean(returns),
        "median_directional_close_return_bps": (
            float(median(returns)) if returns else None
        ),
        "mean_favorable_excursion_bps": _mean(favorable),
        "mean_adverse_excursion_bps": _mean(adverse),
        "opportunity_capture": summarize_path_opportunities(
            evidence.outcomes,
            hurdles,
        ),
        "independent_opportunity_capture": summarize_path_opportunities(
            independent,
            hurdles,
        ),
    }


def _non_overlapping_count(
    outcomes: Sequence[DirectionalPath], horizon_minutes: int
) -> int:
    return non_overlapping_count(
        [outcome.decision_time_ms for outcome in outcomes], horizon_minutes
    )


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None
