"""Validated future-only V58 exit experiments for the central research ledger."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cohort_active_route_lifecycle_status import (
    load_active_route_lifecycle_statuses,
)
from hypervector.research.cohort_route_lifecycle_values import count, records, text

Record = Mapping[str, object]

_SP500_ROUTE = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500"
_BRENTOIL_ROUTE = (
    "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:BRENTOIL"
)
_SP500_EXPERIMENT_ID = "v58-sp500-lower-activation-profit-lock-future-only-v1"
_EXPERIMENTS = {
    _SP500_EXPERIMENT_ID: _SP500_ROUTE,
    "v58-brentoil-profit-lock-future-only-v1": _BRENTOIL_ROUTE,
}
_PRIOR_SP500_ID = "sp500-breakout-profit-lock-l2-proxy"
_REVISIT_BASIS = "exact_v3_live_source_and_fill_contract_replaces_v1_l2_midpoint_proxy"
_NEW_EVIDENCE_SCOPE = "future_only_both_sides_exact_costed_lifecycles"


@dataclass(frozen=True)
class V58FutureOnlyExperimentContext:
    """Fresh exact-route statuses for V58 future-only exit experiments."""

    statuses: tuple[dict[str, object], ...]
    evidence: dict[str, dict[str, object]]
    execution_authority: str
    lineage: dict[str, dict[str, object]]


def load_v58_future_only_experiment_context(
    overrides: Record,
    audit: Record,
    *,
    overrides_path: Path,
    project_root: Path,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> V58FutureOnlyExperimentContext:
    """Load the frozen SP500 and BRENTOIL future-only experiments."""
    experiment_rows = records(
        overrides.get("active_experiments"), "V58 active experiments"
    )
    bridge = dict(overrides)
    bridge["active_hypotheses"] = experiment_rows
    collection = load_active_route_lifecycle_statuses(
        bridge,
        audit,
        overrides_path=overrides_path,
        project_root=project_root,
        observed_at=observed_at,
        maximum_age_seconds=maximum_age_seconds,
    )
    statuses = tuple(dict(row) for row in collection.statuses)
    _require_exact_experiments(statuses)
    lineage = _load_experiment_lineage(experiment_rows, overrides_path)
    return V58FutureOnlyExperimentContext(
        statuses=statuses,
        evidence=dict(collection.evidence),
        execution_authority="none",
        lineage=lineage,
    )


def attach_v58_future_only_experiment_context(
    report: dict[str, object], context: V58FutureOnlyExperimentContext
) -> None:
    """Attach future-only progress without changing route or live authority."""
    _require_report_contract(report, context)
    if "experiment_ledger" in report:
        raise ValueError("V58 experiment ledger is already attached")
    report["experiment_ledger"] = [
        _ledger_row(row, context.lineage) for row in context.statuses
    ]
    evidence = _mapping(report.get("evidence"), "V58 report evidence")
    if "experiments" in evidence:
        raise ValueError("V58 experiment evidence is already attached")
    evidence["experiments"] = dict(context.evidence)
    evidence["experiment_lineage"] = {
        key: dict(_mapping(value.get("source_evidence"), "lineage evidence"))
        for key, value in context.lineage.items()
    }
    report["future_only_experiment_context"] = {
        "experiment_count": len(context.statuses),
        "execution_authority": "none",
        "automatic_live_change": False,
    }


def _ledger_row(status: Record, lineage: Record) -> dict[str, object]:
    row = dict(status)
    row.update(
        {
            "status": (
                "resolved_review_due"
                if status.get("minimum_diagnostic_evidence_met") is True
                else "being_tested"
            ),
            "automatic_live_change": False,
            "execution_authority": "none",
        }
    )
    hypothesis_id = text(status.get("hypothesis_id"), "experiment id")
    if hypothesis_id in lineage:
        prior = _mapping(lineage[hypothesis_id], "experiment lineage")
        row["prior_disposition"] = {
            field: prior[field]
            for field in ("hypothesis_id", "status", "decision", "falsifier")
        }
        row["revisit_basis"] = prior["revisit_basis"]
        row["new_evidence_scope"] = prior["new_evidence_scope"]
    return row


def _load_experiment_lineage(
    experiments: list[Record], overrides_path: Path
) -> dict[str, dict[str, object]]:
    lineage: dict[str, dict[str, object]] = {}
    for experiment in experiments:
        hypothesis_id = text(experiment.get("hypothesis_id"), "experiment id")
        spec = experiment.get("prior_disposition")
        if spec is None:
            continue
        lineage[hypothesis_id] = _load_prior_disposition(
            _mapping(spec, "prior disposition spec"), overrides_path
        )
    _require_lineage(lineage)
    return lineage


def _load_prior_disposition(spec: Record, overrides_path: Path) -> dict[str, object]:
    source = (
        overrides_path.parent / text(spec.get("source"), "lineage source")
    ).resolve()
    raw = source.read_bytes()
    payload = _mapping(json.loads(raw), "prior disposition")
    evidence = {"path": str(source), **file_evidence(source)}
    expected = {
        "sha256": text(spec.get("sha256"), "lineage sha256"),
        "bytes": count(spec.get("bytes"), "lineage bytes"),
    }
    if any(evidence.get(key) != value for key, value in expected.items()):
        raise ValueError("SP500 prior rejection evidence differs")
    return {
        "hypothesis_id": text(payload.get("hypothesis_id"), "prior hypothesis id"),
        "status": text(payload.get("status"), "prior status"),
        "decision": text(payload.get("decision"), "prior decision"),
        "falsifier": text(payload.get("falsifier"), "prior falsifier"),
        "revisit_basis": text(spec.get("revisit_basis"), "revisit basis"),
        "new_evidence_scope": text(spec.get("new_evidence_scope"), "evidence scope"),
        "source_evidence": evidence,
    }


def _require_lineage(lineage: Record) -> None:
    if set(lineage) != {_SP500_EXPERIMENT_ID}:
        raise ValueError("SP500 prior rejection lineage is missing or aliased")
    prior = _mapping(lineage.get(_SP500_EXPERIMENT_ID), "SP500 prior rejection lineage")
    expected = {
        "hypothesis_id": _PRIOR_SP500_ID,
        "status": "reject",
        "revisit_basis": _REVISIT_BASIS,
        "new_evidence_scope": _NEW_EVIDENCE_SCOPE,
    }
    if any(prior.get(key) != value for key, value in expected.items()):
        raise ValueError("SP500 prior rejection lineage differs")
    for field in ("decision", "falsifier"):
        text(prior.get(field), f"SP500 prior {field}")
    _mapping(prior.get("source_evidence"), "SP500 prior source evidence")


def _require_exact_experiments(statuses: tuple[dict[str, object], ...]) -> None:
    observed: dict[str, str] = {}
    for status in statuses:
        hypothesis_id = text(status.get("hypothesis_id"), "experiment id")
        route = text(status.get("route"), "experiment route")
        if hypothesis_id in observed:
            raise ValueError("V58 future-only experiment ids are duplicated")
        observed[hypothesis_id] = route
        if status.get("required_sides") != ["long", "short"]:
            raise ValueError("V58 future-only experiments require both sides")
    if observed != _EXPERIMENTS:
        raise ValueError("V58 future-only experiment set is incomplete or aliased")


def _require_report_contract(
    report: Record, context: V58FutureOnlyExperimentContext
) -> None:
    contract = _mapping(report.get("contract"), "V58 report contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 continuous report authority differs")
    if context.execution_authority != "none":
        raise ValueError("V58 future-only experiment context has authority")
    _require_exact_experiments(context.statuses)
    _require_lineage(context.lineage)


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value
