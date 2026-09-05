"""Side-aware reconciliation for aggregate route lifecycle evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_route_lifecycle_values import (
    REPORT_CONTRACT,
    count,
    mapping,
    records,
    text,
    text_sequence,
    validate_report_contract,
)

Record = Mapping[str, object]


def reconcile_route_lifecycle_sides(
    status: Record, checkpoint: Record
) -> dict[str, object]:
    """Reconcile exact eligible sides without changing lifecycle authority."""
    identity, required = _status_identity(status)
    readiness = _status_readiness(status)
    progress = _status_progress(status, required)
    side_counts = _checkpoint_side_counts(checkpoint, identity, required, readiness)
    attributable = sum(
        count(progress[side].get("attributable_entries"), f"{side} entries")
        for side in required
    )
    executable = sum(side_counts[side] for side in required)
    if attributable > executable:
        raise ValueError("attributable lifecycles exceed executable-side eligibility")
    excluded = sum(side_counts[side] for side in side_counts if side not in required)
    unattributed = executable - attributable
    return _report(
        status,
        identity,
        progress,
        side_counts,
        executable,
        excluded,
        attributable,
        unattributed,
    )


def _status_identity(status: Record) -> tuple[Record, tuple[str, ...]]:
    if status.get("schema_version") != 1:
        raise ValueError("route lifecycle status schema is invalid")
    if status.get("mode") != "cohort_exact_route_lifecycle_evidence":
        raise ValueError("route lifecycle status mode is invalid")
    validate_report_contract(status.get("contract"), "route lifecycle status")
    if status.get("live_change_supported") is not False:
        raise ValueError("route lifecycle status grants unsupported live change")
    identity = mapping(status.get("identity"), "route lifecycle identity")
    required = tuple(text_sequence(identity.get("required_sides"), "required sides"))
    if not required or any(side not in {"long", "short"} for side in required):
        raise ValueError("required sides must contain long or short")
    route = text(identity.get("route"), "route identity")
    provider = text(identity.get("provider_id"), "provider identity")
    symbol = text(identity.get("symbol"), "symbol identity")
    if route != f"{provider}|{symbol}":
        raise ValueError("route lifecycle identity is inconsistent")
    return identity, required


def _status_readiness(status: Record) -> Record:
    boundary = mapping(status.get("prospective_boundary"), "prospective boundary")
    if count(boundary.get("baseline_eligible"), "baseline eligible") != 0:
        raise ValueError("side reconciliation requires a zero eligible baseline")
    readiness = mapping(status.get("route_readiness"), "route readiness")
    eligible = count(readiness.get("eligible"), "eligible evaluations")
    prospective = count(
        readiness.get("prospective_eligible"), "prospective eligible evaluations"
    )
    if eligible != prospective:
        raise ValueError("zero-baseline prospective eligibility must equal cumulative")
    return readiness


def _status_progress(status: Record, required: Sequence[str]) -> dict[str, Record]:
    progress = mapping(status.get("side_progress"), "side progress")
    if set(progress) != set(required):
        raise ValueError("side progress differs from required execution sides")
    return {side: mapping(progress[side], f"{side} progress") for side in required}


def _checkpoint_side_counts(
    checkpoint: Record,
    identity: Record,
    required: Sequence[str],
    status_readiness: Record,
) -> dict[str, int]:
    validate_report_contract(checkpoint.get("checkpoint_contract"), "checkpoint")
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    validate_report_contract(audit.get("experiment_contract"), "checkpoint audit")
    _require_checkpoint_identity(checkpoint, audit, identity, required)
    route = text(identity.get("route"), "route identity")
    readiness_rows = mapping(
        mapping(audit.get("readiness"), "checkpoint readiness").get(
            "by_provider_symbol"
        ),
        "checkpoint route readiness",
    )
    checkpoint_readiness = mapping(readiness_rows.get(route), "selected readiness")
    _require_same_readiness(checkpoint_readiness, status_readiness)
    outcomes = mapping(audit.get("signal_outcomes"), "signal outcomes")
    routes = mapping(outcomes.get("by_provider_symbol"), "route signal outcomes")
    route_outcomes = mapping(routes.get(route), "selected route signal outcomes")
    counts = _side_counts(route_outcomes)
    eligible = count(status_readiness.get("eligible"), "eligible evaluations")
    if sum(counts.values()) != eligible:
        raise ValueError("eligible side counts do not reconcile to route eligibility")
    return counts


def _require_checkpoint_identity(
    checkpoint: Record, audit: Record, identity: Record, required: Sequence[str]
) -> None:
    generation = mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    fingerprint = text(identity.get("profile_fingerprint"), "profile fingerprint")
    if generation.get("matches_runtime") is not True:
        raise ValueError("side reconciliation requires the current configuration")
    for field in ("current_profile_fingerprint", "runtime_profile_fingerprint"):
        if generation.get(field) != fingerprint:
            raise ValueError(f"configuration {field.replace('_', ' ')} mismatch")
    directions = mapping(
        generation.get("current_provider_execution_directions"),
        "provider execution directions",
    )
    route = text(identity.get("route"), "route identity")
    if tuple(text_sequence(directions.get(route), "route directions")) != tuple(
        required
    ):
        raise ValueError("route execution directions differ from frozen sides")
    _require_run_identity(mapping(audit.get("run"), "audit run"), identity)


def _require_run_identity(run: Record, identity: Record) -> None:
    for field in ("run_id", "profile_id", "profile_fingerprint"):
        if run.get(field) != identity.get(field):
            raise ValueError(f"audit {field.replace('_', ' ')} mismatch")


def _require_same_readiness(checkpoint: Record, status: Record) -> None:
    pairs = (
        ("count", "evaluations"),
        ("eligible", "eligible"),
    )
    for checkpoint_field, status_field in pairs:
        observed = count(checkpoint.get(checkpoint_field), checkpoint_field)
        expected = count(status.get(status_field), status_field)
        if observed != expected:
            raise ValueError("checkpoint and lifecycle status readiness differ")


def _side_counts(route_outcomes: Record) -> dict[str, int]:
    by_side = mapping(route_outcomes.get("by_side"), "signal outcomes by side")
    if set(by_side) != {"long", "short"}:
        raise ValueError("signal outcomes require exact long and short sides")
    counts = {
        side: count(
            mapping(by_side[side], f"{side} signal outcomes").get(
                "eligible_evaluations"
            ),
            f"{side} eligible evaluations",
        )
        for side in ("long", "short")
    }
    aggregate = count(
        route_outcomes.get("eligible_evaluations"), "signal eligible evaluations"
    )
    if sum(counts.values()) != aggregate:
        raise ValueError("signal outcome side counts do not reconcile")
    return counts


def _report(
    status: Record,
    identity: Record,
    progress: Mapping[str, Record],
    side_counts: Mapping[str, int],
    executable: int,
    excluded: int,
    attributable: int,
    unattributed: int,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_exact_route_lifecycle_side_reconciliation",
        "observed_at_utc": status.get("observed_at_utc"),
        "state": _state(status, progress, unattributed),
        "contract": dict(REPORT_CONTRACT),
        "identity": dict(identity),
        "source_state": status.get("state"),
        "side_eligibility": {
            "prospective_by_side": dict(side_counts),
            "executable_side_eligible_evaluations": executable,
            "excluded_side_eligible_evaluations": excluded,
            "attributable_executable_lifecycles": attributable,
            "unattributed_executable_side_eligible_evaluations": unattributed,
        },
        "side_progress": {side: dict(row) for side, row in progress.items()},
        "live_change_supported": False,
    }


def _state(status: Record, progress: Mapping[str, Record], unattributed: int) -> str:
    unresolved = records(status.get("unresolved_lifecycles"), "unresolved lifecycles")
    opened = records(status.get("open_lifecycles"), "open lifecycles")
    if unresolved or any(
        mapping(row, "open lifecycle").get("missing_evidence_fields") for row in opened
    ):
        return "technical_evidence_pending"
    if unattributed:
        return "eligible_evidence_unattributed"
    if status.get("minimum_diagnostic_evidence_met") is True:
        return "diagnostic_minimum_complete"
    if opened:
        return "tracking_open_lifecycle"
    pending = [
        side for side, row in progress.items() if row.get("minimum_met") is not True
    ]
    return f"awaiting_{pending[0]}" if len(pending) == 1 else "awaiting_both_sides"
