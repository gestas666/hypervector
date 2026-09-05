"""Exact current-run signal scarcity and missed-opportunity diagnostics."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from math import isfinite

from hypervector.research.cohort_decision_side_coverage import (
    build_decision_side_coverage,
)
from hypervector.research.cohort_live_diagnostic_disposition import (
    apply_closed_path_dispositions,
)
from hypervector.research.cohort_opportunity_episode_evidence import (
    episode_attribution_assessment,
    match_episode_capture,
    parse_episode_attributions,
    validated_blocker_episode_evidence,
)

Record = Mapping[str, object]
_MINIMUM_INDEPENDENT_PATHS = 3
_CONTRACT: dict[str, object] = {
    "report_only": True,
    "execution_authority": "none",
    "automatic_live_change": False,
    "performance_gate": False,
}


def build_live_opportunity_diagnostics(
    audit: Record, *, hypothesis_decisions: object = None
) -> dict[str, object]:
    """Expose exact route readiness paths without claiming hypothetical fills."""
    signal = _mapping(audit.get("signal_outcomes"), "signal outcomes")
    outcomes = _mapping(signal.get("by_provider_symbol"), "route outcomes")
    episode_attributions = parse_episode_attributions(signal)
    readiness = _route_mapping(audit, "readiness")
    scorecard = _route_mapping(audit, "strategy_scorecard")
    configured_routes = set(readiness)
    if configured_routes != set(scorecard):
        raise ValueError("live diagnostic configured route scope is inconsistent")
    if not set(outcomes).issubset(configured_routes):
        raise ValueError("live diagnostic outcome route scope is inconsistent")
    routes = [
        _route_record(
            route,
            outcomes.get(route),
            readiness[route],
            scorecard[route],
            outcomes_available=route in outcomes,
            episode_attributions=episode_attributions,
        )
        for route in sorted(configured_routes)
    ]
    routes = apply_closed_path_dispositions(
        routes, [] if hypothesis_decisions is None else hypothesis_decisions
    )
    leads = [
        path
        for route in routes
        for path in route["one_blocker_paths"]
        if path["assessment"] == "robust_report_only_research_lead"
    ]
    return {
        "status": "available" if routes else "unavailable_no_route_outcomes",
        "contract": dict(_CONTRACT),
        "observation_window": _observation_window(audit),
        "totals": _totals(signal),
        "routes": routes,
        "robust_report_only_leads": leads,
        "limitations": _limitations(),
    }


def _route_mapping(audit: Record, field: str) -> Record:
    section = _mapping(audit.get(field), field.replace("_", " "))
    return _mapping(section.get("by_provider_symbol"), f"{field} routes")


def _route_record(
    route: str,
    raw_outcomes: object | None,
    raw_readiness: object,
    raw_score: object,
    *,
    outcomes_available: bool,
    episode_attributions: list[Record],
) -> dict[str, object]:
    outcomes, evaluations, eligible_count = _route_outcome_evidence(
        route, raw_outcomes, outcomes_available
    )
    readiness = _mapping(raw_readiness, f"route readiness {route}")
    score = _mapping(raw_score, f"route scorecard {route}")
    readiness_count = _nonnegative_int(readiness.get("count"), "readiness")
    combinations = _blocker_combinations(
        readiness.get("blocker_combinations"), readiness_count
    )
    episode_evidence = validated_blocker_episode_evidence(readiness, readiness_count)
    current_execution = _current_live_execution(score)
    return {
        "route": route,
        "signal_outcomes_status": _outcome_status(outcomes_available),
        "outcome_evaluations": evaluations,
        "readiness_evaluations": readiness_count,
        "eligible_evaluations": eligible_count,
        "decision_side_coverage": build_decision_side_coverage(
            outcomes, evaluations, eligible_count
        ),
        "latest_readiness_fraction": _probability(
            readiness.get("latest_fraction"), "readiness fraction"
        ),
        "latest_blockers": _text_list(readiness.get("latest_blockers"), "blockers"),
        "blocker_counts": _counts(readiness.get("blockers"), "blocker counts"),
        "blocker_combinations": combinations,
        "blocker_combination_status": (
            "available" if combinations else "unavailable_legacy_audit"
        ),
        **episode_evidence,
        "historical_cadence": _optional_text(score.get("historical_cadence")),
        "historical_cadence_currentness": (
            "superseded_by_current_live_execution"
            if current_execution["closed_lifecycles"]
            else "frozen_prior_evidence"
        ),
        "current_live_execution": current_execution,
        "scarcity_interpretation": _scarcity(evaluations, eligible_count),
        "one_blocker_paths": _one_blocker_paths(route, outcomes, episode_attributions),
    }


def _outcome_status(available: bool) -> str:
    if available:
        return "available"
    return "unavailable_no_completed_route_evaluation"


def _route_outcome_evidence(
    route: str,
    raw_outcomes: object | None,
    available: bool,
) -> tuple[Record, int, int]:
    if not available:
        return {}, 0, 0
    outcomes = _mapping(raw_outcomes, f"route outcomes {route}")
    evidence = _mapping(outcomes.get("by_evidence_class"), "evidence classes")
    eligible = _mapping(evidence.get("eligible_signal"), "eligible evidence")
    evaluations = _nonnegative_int(outcomes.get("evaluations"), "evaluations")
    eligible_count = _nonnegative_int(eligible.get("evaluations"), "eligible count")
    return outcomes, evaluations, eligible_count


def _current_live_execution(score: Record) -> dict[str, object]:
    identifiable = score.get("execution_outcomes_identifiable", False)
    if not isinstance(identifiable, bool):
        raise ValueError("execution outcome identity must be boolean")
    if not identifiable:
        return _empty_live_execution()
    performance = _mapping(score.get("execution_performance"), "current live execution")
    repeatability = _mapping(
        score.get("repeatability_evidence", {}), "repeatability evidence"
    )
    sides = _mapping(score.get("execution_performance_by_side", {}), "execution sides")
    observed_sides = sorted(sides)
    if not set(observed_sides).issubset({"long", "short"}):
        raise ValueError("execution sides must be long or short")
    return {
        "status": "resolved_lifecycles_available",
        "closed_lifecycles": _nonnegative_int(
            performance.get("closed_trades"), "closed lifecycles"
        ),
        "observed_sides": observed_sides,
        "wins": _nonnegative_int(performance.get("wins"), "wins"),
        "losses": _nonnegative_int(performance.get("losses"), "losses"),
        "breakeven": _nonnegative_int(performance.get("breakeven"), "breakeven"),
        "net_pnl_usd": _number(performance.get("net_pnl_usd"), "net PnL"),
        "fees_usd": _number(performance.get("fees_usd"), "fees"),
        "funding_usd": _number(performance.get("funding_usd"), "funding"),
        "net_return_on_margin_pct": _number(
            performance.get("net_return_on_margin_pct"), "return on margin"
        ),
        "largest_winner_share_of_gross_profit_pct": _optional_number(
            repeatability.get("largest_winner_share_of_gross_profit_pct")
        ),
        "net_pnl_excluding_largest_winner_usd": _optional_number(
            repeatability.get("net_pnl_excluding_largest_winner_usd")
        ),
    }


def _empty_live_execution() -> dict[str, object]:
    return {
        "status": "no_resolved_lifecycles",
        "closed_lifecycles": 0,
        "observed_sides": [],
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "net_pnl_usd": 0.0,
        "fees_usd": 0.0,
        "funding_usd": 0.0,
        "net_return_on_margin_pct": None,
        "largest_winner_share_of_gross_profit_pct": None,
        "net_pnl_excluding_largest_winner_usd": None,
    }


def _blocker_combinations(value: object, expected: int) -> list[dict[str, object]]:
    """Validate exact blocker-set counts when supplied by the live audit."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("blocker combinations must be an array")
    rows = [_blocker_combination(row) for row in value]
    if sum(row["evaluations"] for row in rows) != expected:
        raise ValueError("blocker combination counts do not match readiness")
    return rows


def _blocker_combination(value: object) -> dict[str, object]:
    record = _mapping(value, "blocker combination")
    blockers = _text_list(record.get("blockers"), "combination blockers")
    if blockers != sorted(set(blockers)):
        raise ValueError("combination blockers must be sorted and unique")
    return {
        "blockers": blockers,
        "evaluations": _nonnegative_int(
            record.get("evaluations"), "combination evaluations"
        ),
    }


def _one_blocker_paths(
    route: str, outcomes: Record, episode_attributions: list[Record]
) -> list[dict[str, object]]:
    section = _mapping(outcomes.get("one_blocker_near_misses", {}), "near misses")
    blockers = _mapping(section.get("by_blocker", {}), "near-miss blockers")
    rows: list[dict[str, object]] = []
    for blocker, raw in sorted(blockers.items()):
        record = _mapping(raw, f"near-miss blocker {blocker}")
        horizons = _mapping(record.get("horizons"), "near-miss horizons")
        for horizon, raw_horizon in sorted(horizons.items(), key=_horizon_key):
            episode, attribution_count, ambiguous_count = match_episode_capture(
                episode_attributions, route, blocker, horizon
            )
            rows.append(
                _path_record(
                    route,
                    blocker,
                    horizon,
                    raw_horizon,
                    record,
                    episode,
                    attribution_count,
                    ambiguous_count,
                )
            )
    return rows


def _path_record(
    route: str,
    blocker: str,
    horizon: str,
    raw_horizon: object,
    blocker_record: Record,
    episode: Record | None,
    episode_attribution_count: int,
    ambiguous_episode_attribution_count: int,
) -> dict[str, object]:
    values = _mapping(raw_horizon, f"near-miss horizon {horizon}")
    capture, sample_basis, sample = _ranking_capture(
        values,
        episode,
        episode_attribution_count,
        ambiguous_episode_attribution_count,
    )
    resolved = _nonnegative_int(capture.get("resolved"), "independent resolved")
    mean = _optional_number(capture.get("mean_close_after_estimated_friction_bps"))
    ex_largest = _optional_number(
        capture.get("mean_excluding_largest_close_after_estimated_friction_bps")
    )
    missing = _nonnegative_int(sample.get("missing_data"), "missing data")
    return {
        "route": route,
        "blocker": blocker,
        "horizon_minutes": _positive_int_text(horizon, "horizon"),
        "blocker_evaluations": _nonnegative_int(
            blocker_record.get("evaluations"), "blocker evaluations"
        ),
        "independent_resolved": resolved,
        "censored": _nonnegative_int(sample.get("censored"), "censored"),
        "missing_data": missing,
        "mean_after_estimated_friction_bps": mean,
        "mean_excluding_largest_bps": ex_largest,
        "sample_basis": sample_basis,
        "episode_attribution_count": episode_attribution_count,
        "ambiguous_episode_attribution_count": (ambiguous_episode_attribution_count),
        "cost_clearing_close_rate": _optional_probability(
            capture.get("cost_clearing_close_rate"), "cost-clearing rate"
        ),
        "assessment": episode_attribution_assessment(
            ambiguous_episode_attribution_count,
            episode_attribution_count,
            _path_assessment(resolved, missing, mean, ex_largest),
        ),
        "execution_claim": False,
        "automatic_live_change": False,
    }


def _ranking_capture(
    values: Record,
    episode: Record | None,
    attribution_count: int,
    ambiguous_count: int,
) -> tuple[Record, str, Record]:
    if ambiguous_count:
        capture, _ = _path_capture(values)
        return capture, "portfolio_attribution_ambiguous", values
    if attribution_count == 1 and episode is not None:
        capture = _mapping(
            episode.get("independent_opportunity_capture"),
            "portfolio episode-onset independent capture",
        )
        return capture, "portfolio_episode_onsets", episode
    if attribution_count > 1:
        capture, _ = _path_capture(values)
        return capture, "side_separated_episode_evidence", values
    capture, basis = _path_capture(values)
    return capture, basis, values


def _path_capture(values: Record) -> tuple[Record, str]:
    episode = values.get("episode_onsets")
    if episode is not None:
        onset = _mapping(episode, "episode-onset evidence")
        return (
            _mapping(
                onset.get("independent_opportunity_capture"),
                "episode-onset independent capture",
            ),
            "episode_onsets",
        )
    return (
        _mapping(values.get("independent_opportunity_capture"), "independent capture"),
        "legacy_non_overlapping_paths",
    )


def _path_assessment(
    resolved: int,
    missing: int,
    mean: float | None,
    ex_largest: float | None,
) -> str:
    if missing:
        return "technical_gaps_present"
    if resolved < _MINIMUM_INDEPENDENT_PATHS:
        return "insufficient_independent_paths"
    if mean is None or ex_largest is None or mean <= 0.0 or ex_largest <= 0.0:
        return "negative_or_concentrated_after_estimated_friction"
    return "robust_report_only_research_lead"


def _scarcity(evaluations: int, eligible: int) -> str:
    if eligible:
        return "eligible_signal_observed"
    if not evaluations:
        return "no_completed_route_evaluations"
    return "zero_eligible_signal_observed_no_frequency_conclusion"


def _observation_window(audit: Record) -> dict[str, object]:
    run = _mapping(audit.get("run"), "audit run")
    start = _timestamp(run.get("first_observed_at_utc"), "window start")
    end = _timestamp(run.get("last_observed_at_utc"), "window end")
    if end < start:
        raise ValueError("live diagnostic observation window is reversed")
    return {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "duration_seconds": (end - start).total_seconds(),
    }


def _totals(signal: Record) -> dict[str, int]:
    coverage = _mapping(signal.get("coverage"), "signal coverage")
    return {
        "evaluations": _nonnegative_int(signal.get("evaluations"), "evaluations"),
        "eligible_evaluations": _nonnegative_int(
            signal.get("eligible_evaluations"), "eligible evaluations"
        ),
        "directional_evaluations": _nonnegative_int(
            signal.get("directional_evaluations"), "directional evaluations"
        ),
        "right_censored_observations": _nonnegative_int(
            coverage.get("right_censored_observations"), "right censored"
        ),
    }


def _limitations() -> list[str]:
    return [
        "readiness paths are completed-candle counterfactuals, not orders or fills",
        "zero eligible signals over one window does not estimate long-run frequency",
        "friction estimates omit unknown counterfactual queue and impact effects",
        "a research lead cannot route, resize, retune, or promote a live strategy",
    ]


def _horizon_key(item: tuple[str, object]) -> int:
    return _positive_int_text(item[0], "horizon")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _counts(value: object, label: str) -> dict[str, int]:
    raw = _mapping(value, label)
    return {str(key): _nonnegative_int(count, label) for key, count in raw.items()}


def _text_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of text")
    return list(value)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("optional text must be non-empty")
    return value.strip()


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _positive_int_text(value: str, label: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be positive integer text") from exc
    if parsed <= 0:
        raise ValueError(f"{label} must be positive integer text")
    return parsed


def _probability(value: object, label: str) -> float:
    parsed = _number(value, label)
    if not 0.0 <= parsed <= 1.0:
        raise ValueError(f"{label} must be between zero and one")
    return parsed


def _optional_probability(value: object, label: str) -> float | None:
    return None if value is None else _probability(value, label)


def _optional_number(value: object) -> float | None:
    return None if value is None else _number(value, "optional number")


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError(f"{label} must be finite")
    return parsed


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include timezone")
    return parsed
