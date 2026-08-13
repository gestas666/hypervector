"""Deterministic report-only technical acceptance for an exact v31 run."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.research.cohort_live_audit_values import (
    mapping,
    nonnegative_int,
    number,
    text,
    text_list,
)

Record = Mapping[str, object]

_CANDIDATE_PROFILE = "multi_asset_bidirectional_swing_pruned_candidate_v31"
_PRESSURE_METRICS = ("imbalance_10", "pressure_age_seconds")
PRESSURE_ROUTES: tuple[str, ...] = (
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SP500",
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SPCX",
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1|xyz:SNDK",
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1|xyz:GOLD",
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1|xyz:BRENTOIL",
)


def build_v31_poststart_acceptance(
    checkpoint: Record,
    route_snapshot: Record,
    *,
    maximum_pressure_age_seconds: float = 30.0,
) -> dict[str, object]:
    """Return an execution-incapable accepted/rejected v31 technical report."""
    return build_candidate_poststart_acceptance(
        checkpoint,
        route_snapshot,
        expected_profile_id=_CANDIDATE_PROFILE,
        expected_phase="candidate_v31_forward",
        schema_version="v31_poststart_acceptance_v1",
        maximum_pressure_age_seconds=maximum_pressure_age_seconds,
    )


def build_candidate_poststart_acceptance(
    checkpoint: Record,
    route_snapshot: Record,
    *,
    expected_profile_id: str,
    expected_phase: str,
    schema_version: str,
    maximum_pressure_age_seconds: float = 30.0,
) -> dict[str, object]:
    """Return report-only technical acceptance for one exact candidate identity."""
    _require_identifier(expected_profile_id, "candidate profile")
    _require_identifier(expected_phase, "candidate phase")
    _require_identifier(schema_version, "acceptance schema")
    maximum_age = number(maximum_pressure_age_seconds, "maximum pressure age")
    if maximum_age <= 0.0:
        raise ValueError("maximum pressure age must be positive")
    contract = _contract(route_snapshot)
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    checks = {
        "candidate_identity": _identity_check(
            route_snapshot, expected_profile_id, expected_phase
        ),
        "audit_coverage": _audit_coverage_check(audit),
        "signal_outcome_coverage": _signal_coverage_check(audit),
        "runtime_health": _health_check(audit, route_snapshot),
        "open_position_protection": _protection_check(route_snapshot),
        "transition_drain": _drain_check(checkpoint),
    }
    pressure, pressure_reasons = _pressure_check(audit, maximum_age)
    checks["hip3_pressure_telemetry"] = pressure
    reasons = [
        str(check["reason"])
        for check in checks.values()
        if check["passed"] is False and check.get("reason") is not None
    ]
    reasons.extend(pressure_reasons)
    accepted = not reasons
    return {
        "schema_version": schema_version,
        "contract": contract,
        "accepted": accepted,
        "decision": "accepted" if accepted else "rejected",
        "reasons": reasons,
        "source_checkpoint_generated_at_utc": text(
            checkpoint.get("generated_at_utc"), "checkpoint generation time"
        ),
        "run": dict(mapping(route_snapshot.get("source_run"), "source run")),
        "checks": checks,
        "limitations": _limitations(),
    }


def _contract(route_snapshot: Record) -> dict[str, object]:
    source = mapping(route_snapshot.get("contract"), "route snapshot contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_transition": False,
        "runtime_strategy_changed": False,
    }
    for field, value in expected.items():
        if source.get(field) != value:
            raise ValueError(f"route snapshot has invalid {field}")
    return expected


def _identity_check(
    route_snapshot: Record, expected_profile_id: str, expected_phase: str
) -> dict[str, object]:
    run = mapping(route_snapshot.get("source_run"), "source run")
    candidate = mapping(route_snapshot.get("candidate"), "candidate identity")
    run_profile = text(run.get("profile_id"), "run profile")
    run_fingerprint = text(run.get("profile_fingerprint"), "run fingerprint")
    candidate_fingerprint = text(
        candidate.get("profile_fingerprint"), "candidate fingerprint"
    )
    passed = (
        route_snapshot.get("phase") == expected_phase
        and run_profile == expected_profile_id
        and candidate.get("profile_id") == expected_profile_id
        and run_fingerprint == candidate_fingerprint
        and candidate.get("both_directions") is True
    )
    return {
        "passed": passed,
        "reason": None if passed else "candidate_identity_not_active",
        "phase": route_snapshot.get("phase"),
        "profile_id": run_profile,
        "profile_fingerprint": run_fingerprint,
    }


def _require_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")


def _audit_coverage_check(audit: Record) -> dict[str, object]:
    coverage = mapping(audit.get("coverage"), "audit coverage")
    gaps = text_list(coverage.get("technical_gaps"), "technical gaps")
    passed = coverage.get("complete") is True and not gaps
    return {
        "passed": passed,
        "reason": None if passed else "audit_coverage_incomplete",
        "technical_gaps": gaps,
    }


def _signal_coverage_check(audit: Record) -> dict[str, object]:
    outcomes = mapping(audit.get("signal_outcomes"), "signal outcomes")
    coverage = mapping(outcomes.get("coverage"), "signal outcome coverage")
    without = nonnegative_int(
        coverage.get("evaluations_without_metrics"), "evaluations without metrics"
    )
    gaps = nonnegative_int(coverage.get("metric_value_gaps"), "metric value gaps")
    passed = (
        coverage.get("complete") is True
        and coverage.get("market_data_complete") is True
        and coverage.get("metric_telemetry_complete") is True
        and without == 0
        and gaps == 0
    )
    return {
        "passed": passed,
        "reason": None if passed else "signal_metric_coverage_incomplete",
        "evaluations_without_metrics": without,
        "metric_value_gaps": gaps,
    }


def _health_check(audit: Record, route_snapshot: Record) -> dict[str, object]:
    health = mapping(audit.get("health"), "audit health")
    live = mapping(route_snapshot.get("live_state"), "route live state")
    audit_faults = nonnegative_int(health.get("faults"), "audit faults")
    live_faults = nonnegative_int(live.get("faults"), "live-state faults")
    passed = audit_faults == 0 and live_faults == 0
    return {
        "passed": passed,
        "reason": None if passed else "runtime_faults_present",
        "audit_faults": audit_faults,
        "live_state_faults": live_faults,
    }


def _protection_check(route_snapshot: Record) -> dict[str, object]:
    live = mapping(route_snapshot.get("live_state"), "route live state")
    raw_positions = live.get("open_positions")
    if not isinstance(raw_positions, list):
        raise ValueError("open positions must be a list")
    positions = [mapping(row, "open position") for row in raw_positions]
    unprotected = [
        text(row.get("symbol"), "open position symbol")
        for row in positions
        if row.get("protected_if_open") is not True
    ]
    declared = live.get("all_open_positions_protected")
    if not isinstance(declared, bool):
        raise ValueError("all-open-position protection state must be boolean")
    passed = declared and not unprotected
    return {
        "passed": passed,
        "reason": None if passed else "open_position_unprotected",
        "open_positions": len(positions),
        "unprotected_symbols": unprotected,
    }


def _drain_check(checkpoint: Record) -> dict[str, object]:
    drain = mapping(checkpoint.get("transition_drain"), "transition drain")
    status = text(drain.get("status"), "transition drain status")
    passed = status == "inactive"
    return {
        "passed": passed,
        "reason": None if passed else "transition_drain_not_inactive",
        "status": status,
    }


def _pressure_check(
    audit: Record, maximum_age: float
) -> tuple[dict[str, object], list[str]]:
    outcomes = mapping(audit.get("signal_outcomes"), "signal outcomes")
    by_route = mapping(outcomes.get("by_provider_symbol"), "provider outcomes")
    route_reports: dict[str, object] = {}
    reasons: list[str] = []
    for route in PRESSURE_ROUTES:
        raw = by_route.get(route)
        if not isinstance(raw, Mapping):
            reasons.append(f"pressure_route_missing:{route}")
            route_reports[route] = {"passed": False, "reason": "route_missing"}
            continue
        route_report, route_reasons = _pressure_route(route, raw, maximum_age)
        route_reports[route] = route_report
        reasons.extend(route_reasons)
    return (
        {
            "passed": not reasons,
            "reason": None,
            "maximum_pressure_age_seconds": maximum_age,
            "routes": route_reports,
        },
        reasons,
    )


def _pressure_route(
    route: str, outcome: Record, maximum_age: float
) -> tuple[dict[str, object], list[str]]:
    evaluations = nonnegative_int(outcome.get("evaluations"), f"{route} evaluations")
    diagnostics = mapping(outcome.get("metric_diagnostics"), f"{route} diagnostics")
    coverage = mapping(diagnostics.get("coverage"), f"{route} metric coverage")
    metrics = mapping(diagnostics.get("metrics"), f"{route} metrics")
    reasons = _route_coverage_reasons(route, coverage, evaluations)
    metric_reports: dict[str, object] = {}
    for name in _PRESSURE_METRICS:
        report, reason = _metric_check(route, name, metrics.get(name), evaluations)
        metric_reports[name] = report
        if reason is not None:
            reasons.append(reason)
    age = metric_reports.get("pressure_age_seconds")
    if isinstance(age, Mapping) and age.get("complete") is True:
        minimum = number(age.get("minimum"), f"{route} pressure minimum")
        maximum = number(age.get("maximum"), f"{route} pressure maximum")
        if minimum < 0.0 or maximum > maximum_age:
            reasons.append(f"pressure_age_out_of_bounds:{route}")
    return {
        "passed": not reasons,
        "evaluations": evaluations,
        "coverage_complete": coverage.get("complete") is True,
        "metrics": metric_reports,
    }, reasons


def _route_coverage_reasons(
    route: str, coverage: Record, evaluations: int
) -> list[str]:
    without = nonnegative_int(
        coverage.get("evaluations_without_metrics"), f"{route} missing evaluations"
    )
    gaps = nonnegative_int(coverage.get("metric_value_gaps"), f"{route} metric gaps")
    with_metrics = nonnegative_int(
        coverage.get("evaluations_with_metrics"), f"{route} metric evaluations"
    )
    passed = (
        evaluations > 0
        and coverage.get("complete") is True
        and without == 0
        and gaps == 0
        and with_metrics == evaluations
    )
    return [] if passed else [f"pressure_route_coverage_incomplete:{route}"]


def _metric_check(
    route: str, name: str, raw: object, evaluations: int
) -> tuple[dict[str, object], str | None]:
    if not isinstance(raw, Mapping):
        return {"complete": False}, f"pressure_metric_incomplete:{route}:{name}"
    observations = nonnegative_int(raw.get("observations"), f"{route} {name} count")
    missing = nonnegative_int(raw.get("missing_evaluations"), f"{route} {name} missing")
    values = {
        field: number(raw.get(field), f"{route} {name} {field}")
        for field in ("minimum", "mean", "maximum")
    }
    complete = (
        raw.get("kind") == "numeric"
        and raw.get("value_type") == "float"
        and observations > 0
        and observations == evaluations
        and missing == 0
    )
    return {
        "complete": complete,
        "observations": observations,
        "missing_evaluations": missing,
        **values,
    }, None if complete else f"pressure_metric_incomplete:{route}:{name}"


def _limitations() -> list[str]:
    return [
        "technical acceptance does not establish positive expectancy",
        "aggregate pressure telemetry relies on the hash-bound causal-book repair",
        "acceptance does not authorize transition, orders, resizing, or promotion",
        "historical v25 metric gaps are excluded rather than rewritten",
        "route economics require subsequent resolved same-run lifecycles",
    ]
