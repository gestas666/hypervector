"""Bounded portfolio-wide continuous-improvement research digest."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_hypothesis_ledger import (
    normalize_active_hypotheses,
    normalize_hypothesis_decisions,
)
from hypervector.research.cohort_change_proposals import normalize_change_proposals
from hypervector.research.cohort_first_event_trigger import (
    build_first_event_observations,
)
from hypervector.research.cohort_human_approval import (
    normalize_standing_live_change_approval,
)
from hypervector.research.cohort_side_composition import build_side_composition
from hypervector.research.cohort_successor_triage import build_successor_triage

Record = Mapping[str, object]

_EXPERIMENT_PRIORITY = {
    "collect_and_resolve_source_transport_parity": 0,
    "diagnose_long_entry_quality": 0,
    "shared_portfolio_interaction_replay": 0,
    "collect_both_side_live_execution": 1,
    "collect_route_native_one_blocker_shadow": 1,
    "collect_route_specific_regime_context_evidence": 2,
    "separate_long_short_mechanisms": 2,
    "diagnose_signal_cost_or_concentration": 3,
    "collect_side_specific_evidence": 3,
    "establish_source_backed_mechanism": 4,
    "new_side_mechanic_version_required": 4,
    "new_mechanic_version_required": 5,
}
_FRONTIER_LIMIT = 5
_CONTRACT: dict[str, object] = {
    "report_only": True,
    "execution_authority": "none",
    "automatic_retuning": False,
    "automatic_promotion": False,
    "automatic_strategy_changes": False,
    "runtime_strategy_changed": False,
    "performance_gate": False,
    "trade_count_gate": False,
}


def build_cohort_improvement_digest(
    audit: Record,
    *,
    experiment_overrides: Record | None = None,
) -> dict[str, object]:
    """Rank source-bound research work without execution or promotion authority."""
    triage = build_successor_triage(audit)
    sides = build_side_composition(audit)
    matrix = _validated_matrix(audit)
    matrix_status = _text(matrix.get("availability_status"), "matrix status")
    queue = _experiment_queue(triage)
    queue, override_summary = _apply_experiment_overrides(queue, experiment_overrides)
    near_misses = _robust_near_misses(matrix, triage)
    source = _source_identity(audit)
    return {
        "schema_version": 1,
        "mode": "cohort_portfolio_improvement_digest",
        "contract": dict(_CONTRACT),
        "source": source,
        "performance": _performance(audit),
        "evidence_health": _evidence_health(audit, matrix_status),
        "opportunity_matrix_status": matrix_status,
        "triage_summary": dict(_mapping(triage.get("summary"), "triage summary")),
        "experiment_queue": queue,
        "research_decision_overrides": override_summary,
        "active_hypothesis_observations": build_first_event_observations(
            audit, override_summary["active_hypotheses"]
        ),
        "robust_near_misses": near_misses,
        "side_frontier": _side_frontier(sides),
        "assessment": _assessment(queue, near_misses),
        "limitations": _limitations(),
    }


def _experiment_queue(triage: Record) -> list[dict[str, object]]:
    routes = _mapping(triage.get("routes"), "triage routes")
    queue = [
        _experiment_record(route, _mapping(row, route)) for route, row in routes.items()
    ]
    queue.sort(key=_experiment_sort_key)
    return [dict(row, research_rank=index) for index, row in enumerate(queue, start=1)]


def _apply_experiment_overrides(
    queue: Sequence[Record],
    payload: Record | None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    if payload is None:
        return [dict(row) for row in queue], _empty_override_summary()
    _validate_override_contract(
        _mapping(payload.get("contract"), "research override contract")
    )
    raw_routes = _mapping(payload.get("routes"), "research override routes")
    active = normalize_active_hypotheses(payload.get("active_hypotheses", []))
    decisions = normalize_hypothesis_decisions(payload.get("hypothesis_decisions", []))
    proposals = normalize_change_proposals(payload.get("change_proposals", []))
    review_triggers, trigger_evidence = _review_trigger_inputs(payload)
    approval = normalize_standing_live_change_approval(
        payload.get("standing_live_change_approval")
    )
    indexed = {_text(row.get("route"), "queue route"): dict(row) for row in queue}
    applied: list[str] = []
    sources: dict[str, str] = {}
    for route, raw in sorted(raw_routes.items()):
        if route not in indexed:
            raise ValueError(f"research override references unknown route: {route}")
        override = _mapping(raw, f"research override {route}")
        _apply_route_override(indexed[route], override, route)
        applied.append(route)
        sources[route] = _text(override.get("decision_source"), "decision source")
    updated = list(indexed.values())
    updated.sort(key=_experiment_sort_key)
    ranked = [dict(row, research_rank=index) for index, row in enumerate(updated, 1)]
    return ranked, {
        "applied_routes": applied,
        "decision_sources": sources,
        "active_hypotheses": active,
        "hypothesis_decisions": decisions,
        "change_proposals": proposals,
        "review_triggers": review_triggers,
        "review_trigger_evidence": trigger_evidence,
        "standing_live_change_approval": approval,
        "execution_effect": "report_only",
        "automatic_promotion": False,
    }


def _review_trigger_inputs(
    payload: Record,
) -> tuple[dict[str, object], list[dict[str, str]]]:
    triggers = dict(
        _mapping(payload.get("review_triggers", {}), "research review triggers")
    )
    if not triggers:
        return triggers, []
    evidence = _mapping_sequence(payload.get("evidence", []), "evidence")
    return triggers, [
        {"path": _text(row.get("path"), "research evidence path")} for row in evidence
    ]


def _apply_route_override(row: dict[str, object], override: Record, route: str) -> None:
    triage = _text(override.get("triage"), f"{route} override triage")
    if triage not in {"REVISE", "STOP"}:
        raise ValueError("research decision override cannot promote a route")
    experiment = _text(override.get("next_experiment"), f"{route} override experiment")
    if experiment not in _EXPERIMENT_PRIORITY:
        raise ValueError(f"unsupported research override experiment: {experiment}")
    row.update(
        {
            "triage": triage,
            "next_experiment": experiment,
            "historical_assessment": _text(
                override.get("historical_assessment"),
                f"{route} override historical assessment",
            ),
            "priority_class": _EXPERIMENT_PRIORITY[experiment],
            "decision_source": _text(
                override.get("decision_source"), f"{route} decision source"
            ),
            "supporting_evidence": _text_sequence(
                override.get("supporting_evidence", []),
                f"{route} supporting evidence",
            ),
            "execution_effect": "report_only",
        }
    )


def _validate_override_contract(contract: Record) -> None:
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
    mismatches = [key for key, value in expected.items() if contract.get(key) != value]
    if mismatches:
        raise ValueError(f"research override contract is invalid: {mismatches}")


def _empty_override_summary() -> dict[str, object]:
    return {
        "applied_routes": [],
        "decision_sources": {},
        "active_hypotheses": [],
        "hypothesis_decisions": [],
        "change_proposals": [],
        "review_triggers": {},
        "review_trigger_evidence": [],
        "standing_live_change_approval": None,
        "execution_effect": "report_only",
        "automatic_promotion": False,
    }


def _experiment_record(route: str, row: Record) -> dict[str, object]:
    live = _mapping(row.get("live_translation"), f"{route} live translation")
    forward = _mapping(row.get("forward_path_evidence"), f"{route} forward paths")
    experiment = _text(row.get("next_experiment"), f"{route} next experiment")
    return {
        "route": route,
        "triage": _text(row.get("triage"), f"{route} triage"),
        "next_experiment": experiment,
        "historical_assessment": _text(
            row.get("historical_assessment"), f"{route} historical assessment"
        ),
        "cost_survival": _text(row.get("cost_survival"), f"{route} cost survival"),
        "concentration": _text(row.get("concentration"), f"{route} concentration"),
        "current_profile_closed_trades": _nonnegative_int(
            live.get("closed_trades"), f"{route} closed trades"
        ),
        "current_profile_net_pnl_usd": _number(live.get("net_pnl_usd"), "net PnL"),
        "current_profile_profit_factor": _optional_number(live.get("profit_factor")),
        "observed_sides": _text_sequence(live.get("observed_sides"), "observed sides"),
        "independent_forward_paths": _nonnegative_int(
            forward.get("independent_paths"), f"{route} independent paths"
        ),
        "priority_class": _EXPERIMENT_PRIORITY.get(experiment, 6),
        "execution_effect": "report_only",
    }


def _experiment_sort_key(row: Record) -> tuple[int, int, int, str]:
    return (
        _nonnegative_int(row.get("priority_class"), "priority class"),
        -_nonnegative_int(row.get("current_profile_closed_trades"), "closed trades"),
        -_nonnegative_int(row.get("independent_forward_paths"), "forward paths"),
        _text(row.get("route"), "route"),
    )


def _validated_matrix(audit: Record) -> Record:
    raw = audit.get("execution_opportunity_matrix")
    if raw is None:
        return {
            "availability_status": "unavailable_awaiting_evidence",
            "results": [],
        }
    matrix = _mapping(raw, "opportunity matrix")
    contract = _mapping(matrix.get("contract"), "opportunity matrix contract")
    if contract.get("report_only") is not True:
        raise ValueError("opportunity matrix must be report-only")
    if contract.get("execution_authority") != "none":
        raise ValueError("opportunity matrix execution authority must equal none")
    if contract.get("live_strategy_changed") is not False:
        raise ValueError("opportunity matrix cannot change the live strategy")
    return {**matrix, "availability_status": "available"}


def _robust_near_misses(matrix: Record, triage: Record) -> list[dict[str, object]]:
    routes = _mapping(triage.get("routes"), "triage routes")
    rows = _mapping_sequence(matrix.get("results"), "opportunity results")
    selected = [_near_miss(row, routes) for row in rows if _is_robust_near_miss(row)]
    selected.sort(key=lambda row: (-float(row["net_return_bps"]), str(row["route"])))
    return selected


def _is_robust_near_miss(row: Record) -> bool:
    profit_factor = _optional_number(row.get("profit_factor"))
    ex_largest = _optional_number(row.get("net_return_excluding_largest_winner_bps"))
    return (
        _nonnegative_int(row.get("resolved"), "near-miss resolved") >= 3
        and profit_factor is not None
        and profit_factor > 1.0
        and ex_largest is not None
        and ex_largest > 0.0
    )


def _near_miss(row: Record, routes: Record) -> dict[str, object]:
    route = f"{_text(row.get('strategy_id'), 'near-miss strategy')}|{_text(row.get('symbol'), 'near-miss symbol')}"
    route_triage = _mapping(routes.get(route), f"near-miss triage {route}")
    return {
        "route": route,
        "blocker": _text(row.get("blocker"), "near-miss blocker"),
        "opi_cohort": _text(row.get("opi_cohort"), "near-miss OPI cohort"),
        "resolved": _nonnegative_int(row.get("resolved"), "near-miss resolved"),
        "net_return_bps": _number(row.get("total_net_return_bps"), "near-miss net"),
        "profit_factor": _number(row.get("profit_factor"), "near-miss PF"),
        "net_excluding_largest_winner_bps": _number(
            row.get("net_return_excluding_largest_winner_bps"),
            "near-miss repeatability",
        ),
        "next_experiment": _text(
            route_triage.get("next_experiment"), "next experiment"
        ),
        "identity_status": "generic_path_requires_exact_mechanic_validation",
        "decision": "research_lead_only",
        "automatic_promotion": False,
        "execution_claim": False,
    }


def _source_identity(audit: Record) -> dict[str, object]:
    run = _mapping(audit.get("run"), "audit run")
    return {
        field: _text(run.get(field), f"run {field}")
        for field in (
            "run_id",
            "profile_id",
            "profile_fingerprint",
            "last_observed_at_utc",
        )
    }


def _performance(audit: Record) -> dict[str, object]:
    execution = _mapping(audit.get("execution"), "audit execution")
    portfolio = _mapping(audit.get("portfolio"), "audit portfolio")
    profit_factor = _optional_number(execution.get("profit_factor"))
    return {
        "closed_trades": _nonnegative_int(
            execution.get("closed_trades"), "closed trades"
        ),
        "wins": _nonnegative_int(execution.get("wins"), "wins"),
        "losses": _nonnegative_int(execution.get("losses"), "losses"),
        "net_pnl_usd": _number(execution.get("net_pnl_usd"), "net PnL"),
        "profit_factor": profit_factor,
        "fees_usd": _number(execution.get("fees_usd"), "fees"),
        "funding_usd": _number(execution.get("funding_usd"), "funding"),
        "equity_usd": _number(portfolio.get("final_equity_usd"), "equity"),
        "maximum_drawdown_pct": _number(
            portfolio.get("maximum_drawdown_pct"), "drawdown"
        ),
    }


def _evidence_health(audit: Record, matrix_status: str) -> dict[str, object]:
    coverage = _mapping(audit.get("coverage"), "audit coverage")
    signal = _mapping(audit.get("signal_outcomes"), "signal outcomes")
    signal_coverage = _mapping(signal.get("coverage"), "signal coverage")
    health = _mapping(audit.get("health"), "audit health")
    complete = coverage.get("complete")
    if not isinstance(complete, bool):
        raise ValueError("audit coverage complete must be boolean")
    return {
        "audit_complete": complete,
        "technical_gaps": _text_sequence(
            coverage.get("technical_gaps"), "technical gaps"
        ),
        "metric_value_gaps": _nonnegative_int(
            signal_coverage.get("metric_value_gaps"), "metric value gaps"
        ),
        "right_censored_observations": _nonnegative_int(
            signal_coverage.get("right_censored_observations"), "censored observations"
        ),
        "faults": _nonnegative_int(health.get("faults"), "faults"),
        "opportunity_matrix_available": matrix_status == "available",
    }


def _side_frontier(sides: Record) -> dict[str, object]:
    frontier = _mapping(sides.get("frontier"), "side frontier")
    return {
        side: [dict(row) for row in _mapping_sequence(frontier.get(side), side)][
            :_FRONTIER_LIMIT
        ]
        for side in ("long", "short")
    }


def _assessment(
    queue: Sequence[Record], near_misses: Sequence[Record]
) -> dict[str, object]:
    return {
        "top_research_priority": queue[0]["route"] if queue else None,
        "queued_experiments": len(queue),
        "robust_near_misses": len(near_misses),
        "automatic_action": "none",
        "recommendation": "execute_ranked_report_only_experiments_then_review",
    }


def _limitations() -> list[str]:
    return [
        "ranking orders research work and does not gate or rank live orders",
        "mixed-profile side history is not current-profile edge",
        "near-miss paths are executable-BBO estimates rather than venue fills",
        "generic one-blocker paths do not validate an exact successor identity",
        "open marks and right-censored paths remain provisional",
        "no trade count or performance result automatically promotes or rejects execution",
    ]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _mapping_sequence(value: object, label: str) -> list[Record]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return [_mapping(row, f"{label} row") for row in value]


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _text_sequence(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a text array")
    return list(value)


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        raise ValueError(f"{label} must be finite")
    return result


def _optional_number(value: object) -> float | None:
    return None if value is None else _number(value, "optional numeric value")
