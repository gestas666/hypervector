"""Validated active-route lifecycle statuses for central improvement telemetry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cohort_active_route_side_reconciliation import (
    load_active_route_side_reconciliation,
)
from hypervector.research.cohort_route_lifecycle_values import (
    REPORT_CONTRACT,
    count,
    mapping,
    records,
    text,
    text_sequence,
    timestamp,
)

Record = Mapping[str, object]

_MODE = "cohort_exact_route_lifecycle_evidence"


@dataclass(frozen=True)
class ActiveRouteLifecycleCollection:
    """Validated route summaries and their immutable source evidence."""

    statuses: list[dict[str, object]]
    evidence: dict[str, dict[str, object]]


def load_active_route_lifecycle_statuses(
    overrides: Record,
    audit: Record,
    *,
    overrides_path: Path,
    project_root: Path,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> ActiveRouteLifecycleCollection:
    """Load every declared exact-route collector without changing authority."""
    root = project_root.resolve()
    _validate_time(observed_at, maximum_age_seconds)
    run = mapping(audit.get("run"), "improvement audit run")
    value = overrides.get("active_hypotheses")
    hypotheses = [] if value is None else records(value, "active hypotheses")
    statuses: list[dict[str, object]] = []
    evidence: dict[str, dict[str, object]] = {}
    for hypothesis in hypotheses:
        loaded = _load_hypothesis(
            hypothesis, run, overrides_path, root, observed_at, maximum_age_seconds
        )
        if loaded is None:
            continue
        hypothesis_id, status, source = loaded
        if hypothesis_id in evidence:
            raise ValueError("active route lifecycle hypothesis ids must be unique")
        statuses.append(status)
        evidence[hypothesis_id] = source
    return ActiveRouteLifecycleCollection(statuses, evidence)


def normalize_active_route_lifecycle_statuses(value: object) -> None:
    """Remove polling-only route progress while retaining material outcomes."""
    if not isinstance(value, list):
        return
    for row in value:
        if not isinstance(row, dict):
            continue
        for field in ("observed_at_utc", "age_seconds", "prospective_evaluations"):
            row.pop(field, None)


def _load_hypothesis(
    hypothesis: Record,
    run: Record,
    overrides_path: Path,
    root: Path,
    observed_at: datetime,
    maximum_age: float,
) -> tuple[str, dict[str, object], dict[str, object]] | None:
    status_value = hypothesis.get("lifecycle_status_path")
    if status_value is None:
        return None
    hypothesis_id = text(hypothesis.get("hypothesis_id"), "hypothesis id")
    route = text(hypothesis.get("route"), "hypothesis route")
    sides = text_sequence(hypothesis.get("required_sides"), "required sides")
    if not sides or any(side not in {"long", "short"} for side in sides):
        raise ValueError("required sides must contain long or short")
    status_path = _inside(root, text(status_value, "lifecycle status path"))
    raw = status_path.read_bytes()
    payload = mapping(json.loads(raw), "route lifecycle status")
    _require_contract(payload)
    identity = _require_identity(payload, run, route, sides)
    observed, age = _freshness(payload, observed_at, maximum_age)
    source = _source_evidence(
        payload, status_path, raw, hypothesis, overrides_path, root
    )
    status = _project_status(
        payload, identity, hypothesis_id, route, sides, observed, age
    )
    reconciliation = hypothesis.get("side_reconciliation_path")
    if reconciliation is not None and status["prospective_eligible"] == 0:
        status["side_reconciliation_status"] = "not_required_no_eligible_evidence"
    elif reconciliation is not None:
        reconciliation_path = _inside(
            root, text(reconciliation, "side reconciliation path")
        )
        status, side_evidence = load_active_route_side_reconciliation(
            reconciliation_path, payload, status_path, raw, status
        )
        source["side_reconciliation"] = side_evidence
    return hypothesis_id, status, source


def _require_contract(payload: Record) -> None:
    if payload.get("schema_version") != 1 or payload.get("mode") != _MODE:
        raise ValueError("route lifecycle source contract is invalid")
    contract = mapping(payload.get("contract"), "route lifecycle contract")
    if any(
        contract.get(field) != expected for field, expected in REPORT_CONTRACT.items()
    ):
        raise ValueError("route lifecycle authority contract is invalid")
    if payload.get("live_change_supported") is not False:
        raise ValueError("route lifecycle status cannot support a live change")


def _require_identity(
    payload: Record, run: Record, route: str, sides: list[str]
) -> Record:
    identity = mapping(payload.get("identity"), "route lifecycle identity")
    expected = {
        "run_id": run.get("run_id"),
        "profile_id": run.get("profile_id"),
        "profile_fingerprint": run.get("profile_fingerprint"),
    }
    if any(identity.get(field) != value for field, value in expected.items()):
        raise ValueError("route lifecycle run identity mismatch")
    if identity.get("route") != route:
        raise ValueError("route identity mismatch")
    if text_sequence(identity.get("required_sides"), "status required sides") != sides:
        raise ValueError("route lifecycle side identity mismatch")
    routes = text_sequence(run.get("executable_provider_symbols"), "executable routes")
    if routes and route not in routes:
        raise ValueError("route lifecycle route is not executable")
    provider, separator, symbol = route.partition("|")
    if not separator or identity.get("provider_id") != provider:
        raise ValueError("route lifecycle provider identity mismatch")
    if identity.get("symbol") != symbol:
        raise ValueError("route lifecycle symbol identity mismatch")
    return identity


def _freshness(
    payload: Record, observed_at: datetime, maximum_age: float
) -> tuple[datetime, float]:
    source_time = timestamp(payload.get("observed_at_utc"), "route lifecycle time")
    age = (observed_at.astimezone(UTC) - source_time).total_seconds()
    if age < 0.0:
        raise ValueError("route lifecycle status is from the future")
    if age > maximum_age:
        raise ValueError("route lifecycle status is stale")
    return source_time, age


def _project_status(
    payload: Record,
    identity: Record,
    hypothesis_id: str,
    route: str,
    sides: list[str],
    observed: datetime,
    age: float,
) -> dict[str, object]:
    readiness = _readiness(payload)
    progress = _side_progress(payload, sides)
    lifecycles = _lifecycle_counts(payload, progress)
    minimum_met = _boolean(
        payload.get("minimum_diagnostic_evidence_met"), "diagnostic minimum"
    )
    if minimum_met != all(row["minimum_met"] is True for row in progress.values()):
        raise ValueError("route lifecycle diagnostic minimum is inconsistent")
    return {
        "hypothesis_id": hypothesis_id,
        "route": route,
        "provider_id": identity["provider_id"],
        "symbol": identity["symbol"],
        "required_sides": sides,
        "state": text(payload.get("state"), "route lifecycle state"),
        "observed_at_utc": observed.isoformat(),
        "age_seconds": age,
        "freshness_status": "fresh",
        **readiness,
        **lifecycles,
        "side_progress": progress,
        "minimum_diagnostic_evidence_met": minimum_met,
        "live_change_supported": False,
    }


def _readiness(payload: Record) -> dict[str, int]:
    row = mapping(payload.get("route_readiness"), "route readiness")
    values = {
        field: count(row.get(field), field.replace("_", " "))
        for field in (
            "evaluations",
            "eligible",
            "prospective_evaluations",
            "prospective_eligible",
            "unattributed_eligible_evaluations",
        )
    }
    if values["eligible"] > values["evaluations"]:
        raise ValueError("eligible route evaluations exceed evaluations")
    if values["prospective_evaluations"] > values["evaluations"]:
        raise ValueError("prospective evaluations exceed route evaluations")
    if values["prospective_eligible"] > values["prospective_evaluations"]:
        raise ValueError("prospective eligible exceeds prospective evaluations")
    if values["unattributed_eligible_evaluations"] > values["prospective_eligible"]:
        raise ValueError("unattributed route entries exceed eligible evaluations")
    return values


def _side_progress(payload: Record, sides: list[str]) -> dict[str, dict[str, object]]:
    source = mapping(payload.get("side_progress"), "route side progress")
    if set(source) != set(sides):
        raise ValueError("route side progress differs from required sides")
    output: dict[str, dict[str, object]] = {}
    for side in sides:
        row = mapping(source.get(side), f"{side} route progress")
        output[side] = _project_side(row, side)
    return output


def _project_side(row: Record, side: str) -> dict[str, object]:
    values: dict[str, object] = {
        field: count(row.get(field), f"{side} {field.replace('_', ' ')}")
        for field in (
            "attributable_entries",
            "open_lifecycles",
            "closed_lifecycles",
            "resolved_lifecycles",
        )
    }
    if values["attributable_entries"] != (
        values["open_lifecycles"] + values["closed_lifecycles"]
    ):
        raise ValueError(f"{side} attributable lifecycle count is inconsistent")
    if values["resolved_lifecycles"] > values["closed_lifecycles"]:
        raise ValueError(f"{side} resolved lifecycle count is inconsistent")
    values["minimum_met"] = _boolean(row.get("minimum_met"), f"{side} minimum")
    return values


def _lifecycle_counts(payload: Record, progress: Record) -> dict[str, int]:
    counts = {
        field: len(records(payload.get(field), field.replace("_", " ")))
        for field in (
            "open_lifecycles",
            "closed_lifecycles",
            "resolved_lifecycles",
            "unresolved_lifecycles",
        )
    }
    for field in ("open_lifecycles", "closed_lifecycles", "resolved_lifecycles"):
        expected = sum(
            count(mapping(row, "side progress").get(field), field)
            for row in progress.values()
        )
        if counts[field] != expected:
            raise ValueError(f"route {field.replace('_', ' ')} count is inconsistent")
    if (
        counts["resolved_lifecycles"] + counts["unresolved_lifecycles"]
        != counts["closed_lifecycles"]
    ):
        raise ValueError("route closed lifecycle resolution count is inconsistent")
    return counts


def _source_evidence(
    payload: Record,
    status_path: Path,
    raw: bytes,
    hypothesis: Record,
    overrides_path: Path,
    root: Path,
) -> dict[str, object]:
    declared_prereg = mapping(
        payload.get("preregistration_evidence"), "preregistration evidence"
    )
    prereg = _inside(root, text(declared_prereg.get("path"), "preregistration path"))
    hypothesis_prereg = (
        overrides_path.parent
        / text(hypothesis.get("decision_source"), "decision source")
    ).resolve()
    if prereg != hypothesis_prereg:
        raise ValueError("route lifecycle preregistration path mismatch")
    _require_file_evidence(prereg, declared_prereg, "preregistration evidence mismatch")
    generators = records(payload.get("generator_identity"), "generator identity")
    if not generators:
        raise ValueError("route lifecycle generator identity cannot be empty")
    for generator in generators:
        path = _inside(root, text(generator.get("path"), "generator path"))
        _require_file_evidence(path, generator, "generator evidence mismatch")
    return {
        "path": str(status_path),
        "sha256": file_evidence(status_path)["sha256"],
        "bytes": len(raw),
        "preregistration": dict(declared_prereg),
        "generator_identity": [dict(row) for row in generators],
    }


def _require_file_evidence(path: Path, declared: Record, message: str) -> None:
    actual = file_evidence(path)
    if any(declared.get(field) != actual[field] for field in ("sha256", "bytes")):
        raise ValueError(message)


def _inside(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError("route lifecycle source escapes the project root")
    return path


def _validate_time(observed_at: datetime, maximum_age: float) -> None:
    if observed_at.tzinfo is None:
        raise ValueError("route lifecycle observation time needs a timezone")
    if not math.isfinite(maximum_age) or maximum_age <= 0.0:
        raise ValueError("maximum route lifecycle age must be finite and positive")


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value
