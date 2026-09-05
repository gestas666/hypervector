"""Source-bound side reconciliation for active route lifecycle telemetry."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cohort_route_lifecycle_values import (
    REPORT_CONTRACT,
    count,
    mapping,
    text,
    text_sequence,
)

Record = Mapping[str, object]

_MODE = "cohort_exact_route_lifecycle_side_reconciliation"


def load_active_route_side_reconciliation(
    path: Path,
    source_payload: Record,
    source_path: Path,
    source_raw: bytes,
    projected: Record,
) -> tuple[dict[str, object], dict[str, object]]:
    """Apply one exact side correction and return its source evidence."""
    raw = path.read_bytes()
    payload = mapping(json.loads(raw), "route side reconciliation")
    _require_contract(payload)
    _require_source_identity(payload, source_payload, source_path, source_raw)
    side = _side_eligibility(payload, source_payload)
    output = dict(projected)
    output.update(
        {
            "state": text(payload.get("state"), "side reconciliation state"),
            "unattributed_eligible_evaluations": side[
                "unattributed_executable_side_eligible_evaluations"
            ],
            **side,
            "side_reconciliation_status": "applied",
        }
    )
    evidence = {
        "path": str(path),
        "bytes": len(raw),
        "sha256": file_evidence(path)["sha256"],
        "source_evidence": dict(
            mapping(payload.get("source_evidence"), "side source evidence")
        ),
    }
    return output, evidence


def _require_contract(payload: Record) -> None:
    if payload.get("schema_version") != 1 or payload.get("mode") != _MODE:
        raise ValueError("route side reconciliation contract is invalid")
    contract = mapping(payload.get("contract"), "side reconciliation contract")
    if any(
        contract.get(field) != expected for field, expected in REPORT_CONTRACT.items()
    ):
        raise ValueError("route side reconciliation has execution authority")
    if payload.get("live_change_supported") is not False:
        raise ValueError("route side reconciliation cannot support a live change")


def _require_source_identity(
    payload: Record, source: Record, path: Path, raw: bytes
) -> None:
    identity = mapping(payload.get("identity"), "side reconciliation identity")
    if identity != mapping(source.get("identity"), "route lifecycle identity"):
        raise ValueError("route side reconciliation identity mismatch")
    if payload.get("source_state") != source.get("state"):
        raise ValueError("route side reconciliation source state mismatch")
    if payload.get("side_progress") != source.get("side_progress"):
        raise ValueError("route side reconciliation progress mismatch")
    evidence = mapping(payload.get("source_evidence"), "side source evidence")
    declared = mapping(evidence.get("status"), "side source status evidence")
    expected = {
        "path": str(path.resolve()),
        "bytes": len(raw),
        "sha256": file_evidence(path)["sha256"],
    }
    if dict(declared) != expected:
        raise ValueError("route side reconciliation source bytes mismatch")


def _side_eligibility(payload: Record, source: Record) -> dict[str, object]:
    side = mapping(payload.get("side_eligibility"), "side eligibility")
    by_side = _side_counts(side)
    readiness = mapping(source.get("route_readiness"), "route readiness")
    prospective = count(readiness.get("prospective_eligible"), "prospective eligible")
    if sum(by_side.values()) != prospective:
        raise ValueError("reconciled sides do not match prospective eligibility")
    required = set(
        text_sequence(
            mapping(source.get("identity"), "route identity").get("required_sides"),
            "required sides",
        )
    )
    executable = sum(by_side[item] for item in required)
    excluded = sum(by_side[item] for item in by_side if item not in required)
    values = _eligibility_counts(side)
    if values["executable_side_eligible_evaluations"] != executable:
        raise ValueError("executable-side eligibility is inconsistent")
    if values["excluded_side_eligible_evaluations"] != excluded:
        raise ValueError("excluded-side eligibility is inconsistent")
    if values["unattributed_executable_side_eligible_evaluations"] > executable:
        raise ValueError("unattributed executable eligibility is inconsistent")
    return {"eligible_by_side": by_side, **values}


def _side_counts(side: Record) -> dict[str, int]:
    rows = mapping(side.get("prospective_by_side"), "prospective side eligibility")
    if set(rows) != {"long", "short"}:
        raise ValueError("prospective side eligibility requires long and short")
    return {item: count(rows.get(item), f"{item} eligible") for item in rows}


def _eligibility_counts(side: Record) -> dict[str, int]:
    fields = (
        "executable_side_eligible_evaluations",
        "excluded_side_eligible_evaluations",
        "attributable_executable_lifecycles",
        "unattributed_executable_side_eligible_evaluations",
    )
    values = {
        field: count(side.get(field), field.replace("_", " ")) for field in fields
    }
    if (
        values["attributable_executable_lifecycles"]
        + values["unattributed_executable_side_eligible_evaluations"]
        != values["executable_side_eligible_evaluations"]
    ):
        raise ValueError("executable lifecycle attribution is inconsistent")
    return values
