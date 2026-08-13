"""Fail-closed acceptance of causal HIP-3 startup readiness evidence."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.research.cohort_live_audit_values import mapping, nonnegative_int

Record = Mapping[str, object]


def startup_pressure_route(
    route: str, audit: Record, maximum_age: float
) -> tuple[dict[str, object], list[str]]:
    """Validate one pre-activation pressure seed without treating it as OOS."""
    readiness = mapping(audit.get("readiness"), "audit readiness")
    by_route = mapping(readiness.get("by_provider_symbol"), "provider readiness")
    raw = by_route.get(route)
    if not isinstance(raw, Mapping):
        return {"evidence_source": "missing"}, [f"pressure_route_missing:{route}"]
    metrics = mapping(raw.get("latest_metrics"), f"{route} startup metrics")
    reasons = _startup_pressure_reasons(route, raw, metrics, maximum_age)
    return {
        "passed": not reasons,
        "evaluations": nonnegative_int(raw.get("count"), f"{route} evaluations"),
        "status_counts": {str(metrics.get("pressure_status")): 1},
        "explained_numeric_gaps": 0,
        "evidence_source": "startup_readiness",
    }, reasons


def _startup_pressure_reasons(
    route: str, readiness: Record, metrics: Record, maximum_age: float
) -> list[str]:
    provenance = (
        readiness.get("latest_backend_non_action_reason")
        == "pre_activation_readiness_seed"
        and metrics.get("pressure_status") == "available"
        and metrics.get("pressure_history_complete") is True
        and metrics.get("pressure_scan_complete") is True
        and metrics.get("pressure_source") == "hyperliquid_mainnet_l2_rest"
    )
    imbalance = metrics.get("imbalance_10")
    age = metrics.get("pressure_age_seconds")
    snapshots = metrics.get("pressure_snapshot_count")
    numeric = (
        _bounded_number(imbalance, -1.0, 1.0)
        and _bounded_number(age, 0.0, maximum_age)
        and isinstance(snapshots, int)
        and not isinstance(snapshots, bool)
        and snapshots >= 2
    )
    return [] if provenance and numeric else [f"pressure_startup_incomplete:{route}"]


def _bounded_number(value: object, lower: float, upper: float) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and lower <= float(value) <= upper
    )
