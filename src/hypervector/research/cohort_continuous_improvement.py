"""Report-only continuous-improvement orchestration for a live cohort."""

from __future__ import annotations

from collections.abc import Mapping

Record = Mapping[str, object]

_SIDES = frozenset({"long", "short"})
_PRIORITY = {
    "shared_portfolio_interaction_replay": 0,
    "collect_both_side_live_execution": 1,
    "diagnose_signal_cost_or_concentration": 2,
    "collect_side_specific_evidence": 3,
    "separate_long_short_mechanisms": 4,
    "establish_source_backed_mechanism": 5,
    "new_side_mechanic_version_required": 6,
    "new_mechanic_version_required": 7,
}
_PROPOSAL_FIELDS = [
    "recommendation",
    "why_now",
    "evidence_reviewed",
    "observed_problem_or_opportunity",
    "applicable_market_regime",
    "alternatives_considered",
    "proposed_live_change",
    "expected_upside",
    "main_risks_and_failure_modes",
    "validation_completed",
    "validation_still_required",
    "success_metrics",
    "failure_or_rollback_triggers",
    "confidence_level",
    "explicit_approval_requested",
]


def build_continuous_improvement_report(
    checkpoint: Record,
    digest: Record,
) -> dict[str, object]:
    """Build a traceable research ledger without live execution authority."""
    _validate_contract(checkpoint, "checkpoint_contract")
    _validate_contract(digest, "contract")
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    _validate_identity(audit, digest)
    directions = _configured_directions(checkpoint)
    scores = _scorecard(audit)
    queue = _normalized_queue(digest, directions, scores)
    report = dict(digest)
    report.update(
        {
            "mode": "cohort_continuous_improvement",
            "operational_assessment": _operational_assessment(checkpoint, audit),
            "experiment_queue": queue,
            "hypothesis_ledger": _hypothesis_ledger(queue, scores),
            "highest_value_next_investigation": _highest_value(queue),
            "baseline_comparison": _baseline_comparison(digest),
            "change_proposals": [],
            "proposal_contract": {"required_fields": list(_PROPOSAL_FIELDS)},
            "human_approval_boundary": _approval_boundary(),
        }
    )
    return report


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


def _configured_directions(checkpoint: Record) -> dict[str, list[str]]:
    generation = _mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    if generation.get("matches_runtime") is not True:
        raise ValueError(
            "continuous research requires the current runtime configuration"
        )
    raw = _mapping(
        generation.get("current_provider_execution_directions"), "route directions"
    )
    return {route: _directions(value, route) for route, value in sorted(raw.items())}


def _directions(value: object, route: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"configured directions must be a non-empty array: {route}")
    directions = sorted({_text(side, "configured side") for side in value})
    if set(directions) - _SIDES or len(directions) != len(value):
        raise ValueError(f"configured directions are invalid: {route}")
    return directions


def _scorecard(audit: Record) -> Record:
    scorecard = _mapping(audit.get("strategy_scorecard"), "strategy scorecard")
    return _mapping(scorecard.get("by_provider_symbol"), "scorecard routes")


def _normalized_queue(
    digest: Record,
    directions: Mapping[str, list[str]],
    scores: Record,
) -> list[dict[str, object]]:
    raw_queue = _records(digest.get("experiment_queue"), "experiment queue")
    digest_routes = {_text(row.get("route"), "queue route") for row in raw_queue}
    if digest_routes != set(directions) or digest_routes != set(scores):
        raise ValueError(
            "route scope does not match digest, scorecard, and live config"
        )
    rows = [_normalize_row(row, directions, scores) for row in raw_queue]
    rows.sort(key=_queue_sort_key)
    return [dict(row, research_rank=index) for index, row in enumerate(rows, 1)]


def _normalize_row(
    row: Record,
    directions: Mapping[str, list[str]],
    scores: Record,
) -> dict[str, object]:
    route = _text(row.get("route"), "queue route")
    score = _mapping(scores.get(route), f"scorecard {route}")
    configured = directions[route]
    original = _text(row.get("next_experiment"), "next experiment")
    experiment = _route_experiment(row, score, configured, original)
    return {
        **dict(row),
        "configured_directions": list(configured),
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
) -> str:
    closed = _nonnegative_int(row.get("current_profile_closed_trades"), "closed trades")
    if closed > 0:
        return original
    state = _text(score.get("research_state"), "research state").lower()
    if len(configured) == 1:
        return "collect_side_specific_evidence"
    if "technical_parity_live_outcomes_unresolved" in state:
        return "collect_both_side_live_execution"
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
    queue: list[dict[str, object]], scores: Record
) -> list[dict[str, object]]:
    return [
        _hypothesis_record(row, _mapping(scores.get(row["route"]), "route score"))
        for row in queue
    ]


def _hypothesis_record(row: Record, score: Record) -> dict[str, object]:
    route = _text(row.get("route"), "route")
    directions = _text_list(row.get("configured_directions"), "configured directions")
    return {
        "hypothesis_id": f"v51-live-translation:{route}",
        "route": route,
        "status": "being_tested",
        "configured_directions": directions,
        "hypothesis": "the exact v51 route retains after-cost edge in its intended conditions",
        "experiment": _text(row.get("next_experiment"), "next experiment"),
        "expected_value": "unquantified_until_compatible_forward_lifecycles",
        "confidence": _text(score.get("confidence"), "score confidence"),
        "implementation_complexity": "none_for_observation",
        "downside": "sparse evidence can create false confidence or false rejection",
        "validation_priority": _nonnegative_int(row.get("research_rank"), "rank"),
        "evidence_reviewed": [_text(score.get("evidence_source"), "evidence source")],
        "minimum_additional_evidence": _minimum_evidence(directions),
        "execution_effect": "report_only",
    }


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


def _highest_value(queue: list[dict[str, object]]) -> dict[str, object] | None:
    if not queue:
        return None
    row = queue[0]
    return {
        "route": row["route"],
        "experiment": row["next_experiment"],
        "why_now": "highest-ranked unresolved v51 evidence question",
        "automatic_live_change": False,
    }


def _baseline_comparison(digest: Record) -> dict[str, object]:
    performance = _mapping(digest.get("performance"), "digest performance")
    return {
        "baseline": "v51_current_live_contract",
        "no_action": "continue_current_v51_and_collect_attributable_evidence",
        "compatible_closed_trades": _nonnegative_int(
            performance.get("closed_trades"), "closed trades"
        ),
        "measured_change_delta": None,
        "reason": "no approved change candidate exists",
    }


def _approval_boundary() -> dict[str, object]:
    return {
        "required_before_live_change": True,
        "covered_changes": [
            "strategy",
            "asset_universe",
            "route",
            "parameter",
            "leverage",
            "sizing",
            "risk_control",
            "execution_behavior",
            "deployment_configuration",
        ],
        "current_authority": "research_and_diagnostics_only",
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


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
