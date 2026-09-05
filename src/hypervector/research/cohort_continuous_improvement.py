"""Report-only continuous-improvement orchestration for a live cohort."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.research.cohort_change_proposals import (
    PROPOSAL_FIELDS,
    normalize_change_proposals,
)
from hypervector.research.cohort_continuous_improvement_scope import (
    configured_execution_directions,
    configured_research_directions,
)
from hypervector.research.cohort_hypothesis_ledger import (
    merge_hypothesis_ledger,
    normalize_active_hypotheses,
)
from hypervector.research.cohort_human_approval import build_human_approval_boundary
from hypervector.research.cohort_reconciled_live_diagnostics import (
    build_reconciled_live_diagnostics,
)
from hypervector.research.cohort_mandate_evidence import build_mandate_evidence
from hypervector.research.cohort_opportunity_ranking import (
    rank_research_opportunities,
)
from hypervector.research.cohort_profile_generation import (
    cohort_hypothesis_text,
    cohort_profile_generation,
)
from hypervector.research.cohort_transition_drain_research import (
    build_research_assessment,
    transition_drain_holds_entries,
    with_research_availability,
)

Record = Mapping[str, object]

_PRIORITY = {
    "collect_and_resolve_source_transport_parity": 0,
    "diagnose_long_entry_quality": 0,
    "shared_portfolio_interaction_replay": 0,
    "collect_both_side_forward_paths": 1,
    "collect_both_side_live_execution": 1,
    "collect_route_native_one_blocker_shadow": 1,
    "collect_route_specific_regime_context_evidence": 2,
    "diagnose_signal_cost_or_concentration": 2,
    "collect_side_specific_evidence": 3,
    "separate_long_short_mechanisms": 4,
    "establish_source_backed_mechanism": 5,
    "new_side_mechanic_version_required": 6,
    "new_mechanic_version_required": 7,
}


def build_continuous_improvement_report(
    checkpoint: Record,
    digest: Record,
) -> dict[str, object]:
    """Build a traceable research ledger without live execution authority."""
    _validate_contract(checkpoint, "checkpoint_contract")
    _validate_contract(digest, "contract")
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    _validate_identity(audit, digest)
    directions = configured_research_directions(checkpoint)
    execution_routes = set(configured_execution_directions(checkpoint))
    scores = _scorecard(audit)
    generation = cohort_profile_generation(
        _text(
            _mapping(digest.get("source"), "digest source").get("profile_id"), "profile"
        )
    )
    drain_active = transition_drain_holds_entries(checkpoint)
    queue = with_research_availability(
        _normalized_queue(digest, directions, execution_routes, scores), drain_active
    )
    available = [
        row for row in queue if row["research_availability"] == "available_report_only"
    ]
    ranking = rank_research_opportunities(available, scores)
    report = dict(digest)
    report.update(
        _report_fields(
            checkpoint, digest, audit, queue, ranking, scores, generation, drain_active
        )
    )
    return report


def _report_fields(
    checkpoint: Record,
    digest: Record,
    audit: Record,
    queue: list[dict[str, object]],
    ranking: list[dict[str, object]],
    scores: Record,
    generation: str,
    drain_active: bool,
) -> dict[str, object]:
    return {
        "mode": "cohort_continuous_improvement",
        "assessment": build_research_assessment(
            digest.get("assessment"), ranking, queue, drain_active
        ),
        "operational_assessment": _operational_assessment(checkpoint, audit),
        "experiment_queue": queue,
        "opportunity_ranking": ranking,
        "hypothesis_ledger": _hypothesis_ledger(queue, scores, digest, generation),
        "highest_value_next_investigation": _highest_value(
            ranking, drain_active, generation
        ),
        "baseline_comparison": _baseline_comparison(digest, generation),
        "live_opportunity_diagnostics": build_reconciled_live_diagnostics(
            audit, digest.get("research_decision_overrides")
        ),
        "execution_diagnostics": _execution_diagnostics(audit),
        "mandate_evidence": build_mandate_evidence(audit),
        "change_proposals": _change_proposals(digest),
        "proposal_contract": {
            "required_fields": list(PROPOSAL_FIELDS),
            "execution_authority": "none",
            "automatic_live_change": False,
        },
        "human_approval_boundary": build_human_approval_boundary(
            _standing_approval(digest)
        ),
    }


def _change_proposals(digest: Record) -> list[dict[str, object]]:
    overrides = _optional_mapping(
        digest.get("research_decision_overrides"), "research decision overrides"
    )
    raw = [] if overrides is None else overrides.get("change_proposals", [])
    return normalize_change_proposals(raw)


def _execution_diagnostics(audit: Record) -> dict[str, object]:
    routing_raw = audit.get("routing")
    if routing_raw is None:
        return _unavailable_execution_diagnostics("routing_summary_unavailable")
    routing = _mapping(routing_raw, "routing summary")
    entry_raw = routing.get("entry_age_diagnostics")
    if entry_raw is None:
        return _unavailable_execution_diagnostics("entry_age_evidence_unavailable")
    entry = _mapping(entry_raw, "entry-age diagnostic")
    contract = _mapping(entry.get("contract"), "entry-age diagnostic contract")
    expected = {"report_only": True, "execution_authority": "none"}
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("entry-age diagnostic is not report-only")
    _validate_entry_enforcement(entry, contract)
    executed_late = entry.get("executed_late_entries_proven")
    if not isinstance(executed_late, bool):
        raise ValueError("entry-age late-entry verdict must be boolean")
    return {
        "status": "material_execution_defect" if executed_late else "available",
        "entry_age": dict(entry),
        "execution_effect": "report_only",
        "automatic_live_change": False,
    }


def _validate_entry_enforcement(entry: Record, contract: Record) -> None:
    changed = contract.get("entry_enforcement_changed")
    observed = entry.get("entry_submission_enforcement_observed", False)
    timestamp_observed = entry.get("submission_timestamp_observed")
    if not isinstance(changed, bool) or not isinstance(observed, bool):
        raise ValueError("entry-age enforcement verdict must be boolean")
    if not isinstance(timestamp_observed, bool):
        raise ValueError("entry-age submission timestamp verdict must be boolean")
    if changed != observed:
        raise ValueError("entry-age enforcement contract does not reconcile")
    if changed and not timestamp_observed:
        raise ValueError("entry-age enforcement lacks submission timestamps")


def _unavailable_execution_diagnostics(reason: str) -> dict[str, object]:
    return {
        "status": "unavailable",
        "reason": reason,
        "execution_effect": "report_only",
        "automatic_live_change": False,
    }


def _validate_contract(source: Record, field: str) -> None:
    contract = _mapping(source.get(field), field.replace("_", " "))
    expected = {"report_only": True, "execution_authority": "none"}
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError(f"{field} is not report-only")
    changed = contract.get("runtime_strategy_changed")
    if changed not in {None, False}:
        raise ValueError(f"{field} cannot describe a runtime strategy change")


def _validate_identity(audit: Record, digest: Record) -> None:
    run = _mapping(audit.get("run"), "audit run")
    source = _mapping(digest.get("source"), "digest source")
    fields = ("run_id", "profile_id", "profile_fingerprint")
    if any(
        _text(run.get(field), field) != _text(source.get(field), field)
        for field in fields
    ):
        raise ValueError("digest source identity does not match checkpoint")


def _scorecard(audit: Record) -> Record:
    scorecard = _mapping(audit.get("strategy_scorecard"), "strategy scorecard")
    return _mapping(scorecard.get("by_provider_symbol"), "scorecard routes")


def _normalized_queue(
    digest: Record,
    directions: Mapping[str, list[str]],
    execution_routes: set[str],
    scores: Record,
) -> list[dict[str, object]]:
    raw_queue = _records(digest.get("experiment_queue"), "experiment queue")
    digest_routes = {_text(row.get("route"), "queue route") for row in raw_queue}
    if digest_routes != set(directions) or digest_routes != set(scores):
        raise ValueError(
            "route scope does not match digest, scorecard, and live config"
        )
    rows = [
        _normalize_row(row, directions, scores, execution_routes) for row in raw_queue
    ]
    rows.sort(key=_queue_sort_key)
    return [dict(row, research_rank=index) for index, row in enumerate(rows, 1)]


def _normalize_row(
    row: Record,
    directions: Mapping[str, list[str]],
    scores: Record,
    execution_routes: set[str] | None = None,
) -> dict[str, object]:
    route = _text(row.get("route"), "queue route")
    score = _mapping(scores.get(route), f"scorecard {route}")
    configured = directions[route]
    execution_enabled = execution_routes is None or route in execution_routes
    original = _text(row.get("next_experiment"), "next experiment")
    experiment = _route_experiment(row, score, configured, original, execution_enabled)
    return {
        **dict(row),
        "configured_directions": list(configured),
        "execution_enabled": execution_enabled,
        "base_next_experiment": original,
        "next_experiment": experiment,
        "priority_class": _PRIORITY.get(experiment, 8),
        "side_scope_adjusted": experiment != original,
    }


def _route_experiment(
    row: Record,
    score: Record,
    configured: list[str],
    original: str,
    execution_enabled: bool,
) -> str:
    if not execution_enabled and original == "collect_both_side_live_execution":
        return "collect_both_side_forward_paths"
    if row.get("decision_source") is not None:
        _text(row.get("decision_source"), "decision source")
        return original
    closed = _nonnegative_int(row.get("current_profile_closed_trades"), "closed trades")
    if closed > 0:
        return original
    state = _text(score.get("research_state"), "research state").lower()
    if len(configured) == 1:
        return "collect_side_specific_evidence"
    if "technical_parity_live_outcomes_unresolved" in state:
        return (
            "collect_both_side_live_execution"
            if execution_enabled
            else "collect_both_side_forward_paths"
        )
    if "concentrated" in state or "fold_unstable" in state:
        return "diagnose_signal_cost_or_concentration"
    return original


def _queue_sort_key(row: Record) -> tuple[int, int, str]:
    return (
        _nonnegative_int(row.get("priority_class"), "priority class"),
        _nonnegative_int(row.get("research_rank"), "research rank"),
        _text(row.get("route"), "route"),
    )


def _hypothesis_ledger(
    queue: list[dict[str, object]],
    scores: Record,
    digest: Record,
    generation: str,
) -> list[dict[str, object]]:
    active = [
        _hypothesis_record(
            row, _mapping(scores.get(row["route"]), "route score"), generation
        )
        for row in queue
    ]
    overrides = _optional_mapping(
        digest.get("research_decision_overrides"), "research decision overrides"
    )
    if overrides is not None:
        active.extend(
            normalize_active_hypotheses(overrides.get("active_hypotheses", []))
        )
    historical = [] if overrides is None else overrides.get("hypothesis_decisions", [])
    return merge_hypothesis_ledger(active, historical)


def _hypothesis_record(
    row: Record, score: Record, generation: str
) -> dict[str, object]:
    route = _text(row.get("route"), "route")
    experiment = _text(row.get("next_experiment"), "next experiment")
    directions = _text_list(row.get("configured_directions"), "configured directions")
    output = {
        "hypothesis_id": f"{generation}-live-translation:{route}:{experiment}",
        "route": route,
        "status": "being_tested",
        "configured_directions": directions,
        "hypothesis": cohort_hypothesis_text(experiment, generation),
        "experiment": experiment,
        "expected_value": "unquantified_until_compatible_forward_lifecycles",
        "confidence": _text(score.get("confidence"), "score confidence"),
        "implementation_complexity": "none_for_observation",
        "downside": "sparse evidence can create false confidence or false rejection",
        "validation_priority": _nonnegative_int(row.get("research_rank"), "rank"),
        "evidence_reviewed": _evidence_reviewed(row, score),
        "minimum_additional_evidence": _minimum_evidence(directions),
        "execution_effect": "report_only",
    }
    prospective = row.get("prospective_observation")
    if prospective is not None:
        output["prospective_observation"] = dict(
            _mapping(prospective, "prospective observation")
        )
    return output


def _evidence_reviewed(row: Record, score: Record) -> list[str]:
    """Prefer a frozen decision source while retaining underlying evidence."""
    sources: list[str] = []
    decision_source = row.get("decision_source")
    if decision_source is not None:
        sources.append(_text(decision_source, "decision source"))
    for supporting in _text_list(
        row.get("supporting_evidence", []), "supporting evidence"
    ):
        if supporting not in sources:
            sources.append(supporting)
    evidence_source = _text(score.get("evidence_source"), "evidence source")
    if evidence_source not in sources:
        sources.append(evidence_source)
    return sources


def _minimum_evidence(directions: list[str]) -> dict[str, object]:
    scope = ",".join(directions)
    return {
        "to_update_diagnosis": (
            "at least one attributable eligible signal and one fully resolved lifecycle "
            f"for each configured direction ({scope})"
        ),
        "for_change_recommendation": (
            "a predeclared compatible window with exact fees, funding, slippage, latency, "
            "stop behavior, missed-opportunity review, and largest-winner sensitivity"
        ),
        "promotion_threshold": False,
    }


def _operational_assessment(checkpoint: Record, audit: Record) -> dict[str, object]:
    lifecycle = _mapping(checkpoint.get("lifecycle"), "checkpoint lifecycle")
    health = _mapping(audit.get("health"), "audit health")
    alerts: list[str] = []
    if lifecycle.get("state") != "running_consistent":
        alerts.append("runtime_not_running_consistent")
    if lifecycle.get("backend_process_health") != "healthy":
        alerts.append("backend_process_not_healthy")
    faults = _nonnegative_int(health.get("faults"), "audit faults")
    if faults:
        alerts.append("audit_faults_present")
    faulted_assets = _text_list(lifecycle.get("faulted_assets"), "faulted assets")
    if faulted_assets:
        alerts.append("faulted_assets_present")
    unprotected = _unprotected_assets(health)
    if unprotected:
        alerts.append("open_position_without_venue_protection")
    return {
        "status": "material_defect" if alerts else "healthy",
        "alerts": alerts,
        "faulted_assets": faulted_assets,
        "unprotected_assets": unprotected,
        "heartbeat_age_seconds": _number(
            lifecycle.get("cohort_heartbeat_age_seconds"), "heartbeat age"
        ),
        "escalation_required": bool(alerts),
    }


def _unprotected_assets(health: Record) -> list[str]:
    assets = _mapping(health.get("assets", {}), "asset health")
    unprotected: list[str] = []
    for symbol, raw in assets.items():
        record = _mapping(raw, f"asset health {symbol}")
        position = _number(record.get("position_size_signed", 0.0), "position size")
        if position != 0.0 and record.get("protected_if_open") is not True:
            unprotected.append(symbol)
    return sorted(unprotected)


def _highest_value(
    ranking: list[dict[str, object]], drain_active: bool, generation: str
) -> dict[str, object] | None:
    if not ranking:
        return None
    row = ranking[0]
    return {
        "route": row["route"],
        "experiment": row["experiment"],
        "why_now": (
            "highest-ranked investigation executable during active drain"
            if drain_active
            else f"highest-ranked unresolved {generation} evidence question"
        ),
        "automatic_live_change": False,
    }


def _baseline_comparison(digest: Record, generation: str) -> dict[str, object]:
    performance = _mapping(digest.get("performance"), "digest performance")
    return {
        "baseline": f"{generation}_current_live_contract",
        "no_action": f"continue_current_{generation}_and_collect_attributable_evidence",
        "compatible_closed_trades": _nonnegative_int(
            performance.get("closed_trades"), "closed trades"
        ),
        "measured_change_delta": None,
        "reason": "no approved change candidate exists",
    }


def _standing_approval(digest: Record) -> object:
    overrides = _optional_mapping(
        digest.get("research_decision_overrides"), "research decision overrides"
    )
    return None if overrides is None else overrides.get("standing_live_change_approval")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _optional_mapping(value: object, label: str) -> Record | None:
    return None if value is None else _mapping(value, label)


def _records(value: object, label: str) -> list[Record]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return [_mapping(row, f"{label} row") for row in value]


def _text_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return [_text(item, label) for item in value]


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


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
