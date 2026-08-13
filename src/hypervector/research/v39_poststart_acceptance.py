"""Report-only technical acceptance for the exact v39 live portfolio."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.cohort_live_audit_values import (
    mapping,
    nonnegative_int,
    number,
    text,
    text_list,
)
from hypervector.research.v39_canonical_regime_acceptance import (
    build_canonical_regime_check,
)

Record = Mapping[str, object]

_PROFILE_ID = (
    "multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39"
)
_PRESSURE_PREFIX = "hip3_breakout_pressure_"
_PRESSURE_METRICS = ("imbalance_10", "pressure_age_seconds")
_ALLOWED_PRESSURE_STATUSES = frozenset({"available", "no_candidate", "stale_candidate"})


def build_v39_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    *,
    now_utc: datetime,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float = 30.0,
) -> dict[str, object]:
    """Return an execution-incapable technical verdict for one v39 checkpoint."""
    _require_v39_config(config)
    now = _aware_utc(now_utc, "acceptance clock")
    checkpoint_age = _positive_limit(
        maximum_checkpoint_age_seconds, "maximum checkpoint age"
    )
    pressure_age = _positive_limit(maximum_pressure_age_seconds, "maximum pressure age")
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    checks = _acceptance_checks(
        checkpoint,
        audit,
        config,
        now=now,
        checkpoint_age=checkpoint_age,
        pressure_age=pressure_age,
    )
    reasons = [
        reason
        for check in checks.values()
        for reason in _reason_list(check.get("reasons"), "acceptance reasons")
    ]
    accepted = not reasons
    return {
        "schema_version": "v39_poststart_acceptance_v1",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_strategy_changes": False,
        },
        "accepted": accepted,
        "decision": "accepted" if accepted else "rejected",
        "reasons": reasons,
        "run": dict(mapping(audit.get("run"), "checkpoint run")),
        "checks": checks,
        "limitations": _limitations(),
    }


def _acceptance_checks(
    checkpoint: Record,
    audit: Record,
    config: MultiAssetLiveConfig,
    *,
    now: datetime,
    checkpoint_age: float,
    pressure_age: float,
) -> dict[str, dict[str, object]]:
    return {
        "checkpoint_contract": _contract_check(checkpoint),
        "runtime_identity": _identity_check(audit, config),
        "runtime_freshness": _freshness_check(checkpoint, now, checkpoint_age),
        "runtime_configuration": _generation_check(checkpoint, config),
        "route_identity": _route_check(audit, config),
        "canonical_regime_telemetry": build_canonical_regime_check(
            checkpoint,
            audit,
            maximum_age_seconds=checkpoint_age,
        ),
        "hip3_pressure": _pressure_check(audit, config, pressure_age),
        "open_position_protection": _protection_check(checkpoint, audit, config),
        "friction_and_funding": _friction_check(audit, config),
    }


def _require_v39_config(config: MultiAssetLiveConfig) -> None:
    routes = config.executable_provider_symbols
    directions = config.executable_provider_directions
    exact = (
        config.profile_id == _PROFILE_ID
        and len(config.assets) == 8
        and len(config.providers) == 7
        and len(routes) == 14
        and len(directions) == 28
        and all(
            provider.execution_symbols == provider.symbols
            and provider.sides == frozenset({"long", "short"})
            for provider in config.providers
        )
    )
    if not exact:
        raise ValueError("v39 acceptance requires the exact staged roster contract")


def _contract_check(checkpoint: Record) -> dict[str, object]:
    contract = mapping(checkpoint.get("checkpoint_contract"), "checkpoint contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_pause": False,
        "automatic_retuning": False,
        "runtime_strategy_changed": False,
    }
    reasons = [
        f"checkpoint_contract_invalid:{key}"
        for key, value in expected.items()
        if contract.get(key) != value
    ]
    return _check(reasons, expected=expected)


def _identity_check(audit: Record, config: MultiAssetLiveConfig) -> dict[str, object]:
    run = mapping(audit.get("run"), "checkpoint run")
    routes = _routes(config)
    reasons: list[str] = []
    if text(run.get("profile_id"), "run profile") != config.profile_id:
        reasons.append("runtime_profile_id_mismatch")
    if (
        text(run.get("profile_fingerprint"), "run fingerprint")
        != config.profile_fingerprint
    ):
        reasons.append("runtime_profile_fingerprint_mismatch")
    if set(text_list(run.get("symbols"), "run symbols")) != set(config.symbols):
        reasons.append("runtime_asset_roster_mismatch")
    if set(text_list(run.get("executable_provider_symbols"), "run routes")) != set(
        routes
    ):
        reasons.append("runtime_provider_roster_mismatch")
    if text_list(run.get("observe_only_provider_symbols"), "observe-only routes"):
        reasons.append("observe_only_route_present")
    if nonnegative_int(run.get("maximum_concurrent_positions"), "position limit") != 10:
        reasons.append("runtime_position_limit_mismatch")
    return _check(
        reasons,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        assets=len(config.assets),
    )


def _freshness_check(
    checkpoint: Record,
    now: datetime,
    maximum_age: float,
) -> dict[str, object]:
    generated = _timestamp(checkpoint.get("generated_at_utc"), "checkpoint generation")
    age = (now - generated).total_seconds()
    lifecycle = mapping(checkpoint.get("lifecycle"), "checkpoint lifecycle")
    heartbeat_age = number(
        lifecycle.get("cohort_heartbeat_age_seconds"), "heartbeat age"
    )
    reasons: list[str] = []
    if age < -5.0 or age > maximum_age:
        reasons.append("checkpoint_not_fresh")
    if heartbeat_age < 0.0 or heartbeat_age > maximum_age:
        reasons.append("backend_heartbeat_not_fresh")
    if lifecycle.get("backend_process_health") != "healthy":
        reasons.append("backend_process_not_healthy")
    if lifecycle.get("cohort_heartbeat_status") != "running":
        reasons.append("backend_heartbeat_not_running")
    if lifecycle.get("state") != "running_consistent":
        reasons.append("backend_lifecycle_inconsistent")
    if text_list(lifecycle.get("faulted_assets"), "faulted assets"):
        reasons.append("runtime_faulted_assets_present")
    return _check(
        reasons, checkpoint_age_seconds=age, heartbeat_age_seconds=heartbeat_age
    )


def _generation_check(
    checkpoint: Record, config: MultiAssetLiveConfig
) -> dict[str, object]:
    generation = mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    matching = (
        generation.get("state") == "current_runtime_configuration"
        and generation.get("matches_runtime") is True
        and generation.get("runtime_profile_fingerprint") == config.profile_fingerprint
        and generation.get("current_profile_fingerprint") == config.profile_fingerprint
        and generation.get("execution_authority") == "none"
        and generation.get("automatic_restart") is False
        and not text_list(generation.get("blocking_assets"), "generation blockers")
    )
    reasons = [] if matching else ["runtime_configuration_not_current"]
    return _check(reasons, matches_runtime=generation.get("matches_runtime"))


def _route_check(audit: Record, config: MultiAssetLiveConfig) -> dict[str, object]:
    expected = set(_routes(config))
    routing = mapping(audit.get("routing"), "audit routing")
    routed = set(
        text_list(routing.get("executable_provider_symbols"), "routing routes")
    )
    outcomes = mapping(audit.get("signal_outcomes"), "signal outcomes")
    by_route = mapping(outcomes.get("by_provider_symbol"), "provider outcomes")
    reasons: list[str] = []
    if routed != expected or set(by_route) != expected:
        reasons.append("provider_route_coverage_mismatch")
    for route in sorted(expected.intersection(by_route)):
        report = mapping(by_route[route], f"{route} outcome")
        if nonnegative_int(report.get("evaluations"), f"{route} evaluations") == 0:
            reasons.append(f"provider_route_not_evaluated:{route}")
    return _check(
        reasons,
        provider_symbol_routes=len(expected),
        directional_scopes=len(config.executable_provider_directions),
    )


def _pressure_check(
    audit: Record,
    config: MultiAssetLiveConfig,
    maximum_age: float,
) -> dict[str, object]:
    outcomes = mapping(audit.get("signal_outcomes"), "signal outcomes")
    by_route = mapping(outcomes.get("by_provider_symbol"), "provider outcomes")
    reports: dict[str, object] = {}
    reasons: list[str] = []
    explained = 0
    for route in _pressure_routes(config):
        raw = by_route.get(route)
        if not isinstance(raw, Mapping):
            reasons.append(f"pressure_route_missing:{route}")
            continue
        report, route_reasons = _pressure_route(route, raw, maximum_age)
        reports[route] = report
        reasons.extend(route_reasons)
        explained += int(report["explained_numeric_gaps"])
    reasons.extend(_global_pressure_coverage(audit, explained))
    return _check(
        reasons,
        maximum_pressure_age_seconds=maximum_age,
        explained_numeric_gaps=explained,
        routes=reports,
    )


def _pressure_route(
    route: str, raw: Record, maximum_age: float
) -> tuple[dict[str, object], list[str]]:
    evaluations = nonnegative_int(raw.get("evaluations"), f"{route} evaluations")
    diagnostics = mapping(raw.get("metric_diagnostics"), f"{route} diagnostics")
    coverage = mapping(diagnostics.get("coverage"), f"{route} metric coverage")
    metrics = mapping(diagnostics.get("metrics"), f"{route} metrics")
    status_counts, reasons = _pressure_status(
        route, metrics.get("pressure_status"), evaluations
    )
    available = status_counts.get("available", 0)
    unavailable = evaluations - available
    if available == 0:
        reasons.append(f"pressure_never_available:{route}")
    for name in _PRESSURE_METRICS:
        reasons.extend(
            _numeric_pressure_reasons(
                route, name, metrics.get(name), available, unavailable, maximum_age
            )
        )
    gaps = nonnegative_int(coverage.get("metric_value_gaps"), f"{route} metric gaps")
    expected_gaps = unavailable * len(_PRESSURE_METRICS)
    if gaps != expected_gaps:
        reasons.append(f"pressure_gap_accounting_mismatch:{route}")
    if nonnegative_int(
        coverage.get("evaluations_without_metrics"), f"{route} empty metrics"
    ):
        reasons.append(f"pressure_evaluation_metrics_missing:{route}")
    return {
        "passed": not reasons,
        "evaluations": evaluations,
        "status_counts": status_counts,
        "explained_numeric_gaps": expected_gaps,
    }, reasons


def _pressure_status(
    route: str, raw: object, evaluations: int
) -> tuple[dict[str, int], list[str]]:
    if not isinstance(raw, Mapping):
        return {}, [f"pressure_status_incomplete:{route}"]
    categories = raw.get("categories")
    if not isinstance(categories, list):
        return {}, [f"pressure_status_incomplete:{route}"]
    counts: dict[str, int] = {}
    for item in categories:
        row = mapping(item, f"{route} pressure status category")
        value = text(row.get("value"), f"{route} pressure status")
        counts[value] = nonnegative_int(row.get("count"), f"{route} status count")
    complete = (
        raw.get("kind") == "categorical"
        and raw.get("value_type") == "str"
        and nonnegative_int(raw.get("observations"), f"{route} status observations")
        == evaluations
        and nonnegative_int(raw.get("missing_evaluations"), f"{route} missing status")
        == 0
        and sum(counts.values()) == evaluations
        and set(counts).issubset(_ALLOWED_PRESSURE_STATUSES)
    )
    return counts, [] if complete else [f"pressure_status_incomplete:{route}"]


def _numeric_pressure_reasons(
    route: str,
    name: str,
    raw: object,
    available: int,
    unavailable: int,
    maximum_age: float,
) -> list[str]:
    if not isinstance(raw, Mapping):
        return [f"pressure_metric_incomplete:{route}:{name}"]
    observations = nonnegative_int(raw.get("observations"), f"{route} {name} count")
    missing = nonnegative_int(raw.get("missing_evaluations"), f"{route} {name} missing")
    valid = (
        raw.get("kind") == "numeric"
        and raw.get("value_type") == "float"
        and observations == available
        and missing == unavailable
    )
    if not valid or observations == 0:
        return [f"pressure_metric_incomplete:{route}:{name}"]
    minimum = number(raw.get("minimum"), f"{route} {name} minimum")
    maximum = number(raw.get("maximum"), f"{route} {name} maximum")
    in_bounds = (
        -1.0 <= minimum <= maximum <= 1.0
        if name == "imbalance_10"
        else 0.0 <= minimum <= maximum <= maximum_age
    )
    return [] if in_bounds else [f"pressure_metric_out_of_bounds:{route}:{name}"]


def _global_pressure_coverage(audit: Record, explained: int) -> list[str]:
    outcomes = mapping(audit.get("signal_outcomes"), "signal outcomes")
    coverage = mapping(outcomes.get("coverage"), "signal outcome coverage")
    audit_coverage = mapping(audit.get("coverage"), "audit coverage")
    gaps = nonnegative_int(coverage.get("metric_value_gaps"), "global metric gaps")
    technical = set(text_list(audit_coverage.get("technical_gaps"), "technical gaps"))
    expected_technical = {"provider_metric_telemetry_missing"} if explained else set()
    consistent = (
        gaps == explained
        and coverage.get("market_data_complete") is True
        and nonnegative_int(
            coverage.get("evaluations_without_metrics"), "empty evaluations"
        )
        == 0
        and nonnegative_int(coverage.get("missing_data_observations"), "missing paths")
        == 0
        and nonnegative_int(coverage.get("direction_conflicts"), "direction conflicts")
        == 0
        and technical == expected_technical
        and audit_coverage.get("complete") is (explained == 0)
        and coverage.get("metric_telemetry_complete") is (explained == 0)
        and coverage.get("complete") is (explained == 0)
    )
    return [] if consistent else ["unexplained_signal_metric_coverage_gap"]


def _protection_check(
    checkpoint: Record, audit: Record, config: MultiAssetLiveConfig
) -> dict[str, object]:
    health = mapping(audit.get("health"), "audit health")
    assets = mapping(health.get("assets"), "health assets")
    lifecycle = mapping(checkpoint.get("lifecycle"), "checkpoint lifecycle")
    states = mapping(lifecycle.get("asset_states"), "lifecycle asset states")
    reasons: list[str] = []
    if set(assets) != set(config.symbols) or set(states) != set(config.symbols):
        reasons.append("asset_health_roster_mismatch")
    if nonnegative_int(health.get("faults"), "health faults"):
        reasons.append("runtime_faults_present")
    open_symbols: list[str] = []
    for symbol in sorted(set(config.symbols).intersection(assets)):
        row = mapping(assets[symbol], f"{symbol} health")
        state = text(row.get("final_state"), f"{symbol} final state")
        if states.get(symbol) != state or state not in {"FLAT", "OPEN"}:
            reasons.append(f"asset_state_inconsistent:{symbol}")
        if state == "OPEN":
            open_symbols.append(symbol)
            if row.get("protected_if_open") is not True or row.get("stop_oid") is None:
                reasons.append(f"open_position_unprotected:{symbol}")
    return _check(reasons, open_positions=len(open_symbols), open_symbols=open_symbols)


def _friction_check(audit: Record, config: MultiAssetLiveConfig) -> dict[str, object]:
    execution = mapping(audit.get("execution"), "audit execution")
    friction = mapping(execution.get("friction_parity"), "friction parity")
    by_route = mapping(friction.get("by_provider_symbol"), "friction routes")
    expected = set(_routes(config))
    reasons: list[str] = []
    if set(by_route) != expected:
        reasons.append("friction_route_coverage_mismatch")
    for route in sorted(expected.intersection(by_route)):
        row = mapping(by_route[route], f"{route} friction")
        mismatches = row.get("mismatches")
        if (
            row.get("execution_effect") != "report_only"
            or row.get("parity_state") != "runtime_shape_aligned"
            or not isinstance(mismatches, list)
            or mismatches
        ):
            reasons.append(f"friction_contract_mismatch:{route}")
    fees = number(execution.get("fees_usd"), "execution fees")
    funding = number(execution.get("funding_usd"), "execution funding")
    fills = nonnegative_int(execution.get("current_run_fills"), "current run fills")
    return _check(reasons, fees_usd=fees, funding_usd=funding, fills=fills)


def _routes(config: MultiAssetLiveConfig) -> list[str]:
    return sorted(
        f"{provider}|{symbol}"
        for provider, symbol in config.executable_provider_symbols
    )


def _pressure_routes(config: MultiAssetLiveConfig) -> list[str]:
    return [route for route in _routes(config) if route.startswith(_PRESSURE_PREFIX)]


def _check(reasons: list[str], **evidence: object) -> dict[str, object]:
    return {"passed": not reasons, "reasons": reasons, **evidence}


def _reason_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")
    return list(value)


def _positive_limit(value: float, label: str) -> float:
    parsed = number(value, label)
    if parsed <= 0.0:
        raise ValueError(f"{label} must be positive")
    return parsed


def _timestamp(value: object, label: str) -> datetime:
    raw = text(value, label)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be RFC3339") from exc
    return _aware_utc(parsed, label)


def _aware_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


def _limitations() -> list[str]:
    return [
        "technical acceptance does not establish strategy profitability",
        "explained pressure gaps remain explicit no-trade data-quality evidence",
        "zero fills can verify shape but not realized friction economics",
        "this report cannot route, resize, pause, retune, or submit an order",
        "the $5,000 profile requires a separate funded-account preflight",
    ]
