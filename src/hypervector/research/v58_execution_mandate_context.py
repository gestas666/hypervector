"""Checkpoint-bound execution evidence for the V58 research loop."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cohort_mandate_evidence import build_mandate_evidence

Record = Mapping[str, object]


@dataclass(frozen=True)
class ExecutionMandateContext:
    """Validated report-only execution, trade, and portfolio evidence."""

    payload: dict[str, object]
    evidence: dict[str, object]
    execution_authority: str = "none"


def load_v58_execution_mandate_context(path: Path) -> ExecutionMandateContext:
    """Load one stable checkpoint audit into the shared mandate projection."""
    reference = file_evidence(path)
    raw = path.read_bytes()
    if _raw_evidence(raw) != reference:
        raise ValueError("V58 mandate checkpoint changed while reading")
    document = _mapping(json.loads(raw), "checkpoint")
    _require_report_only(document)
    payload = build_mandate_evidence(_mapping(document.get("audit"), "audit"))
    if file_evidence(path) != reference:
        raise ValueError("V58 mandate checkpoint changed during evaluation")
    evidence = {"checkpoint": {"path": str(path.resolve()), **reference}}
    return ExecutionMandateContext(payload=payload, evidence=evidence)


def execution_mandate_context_payload(
    context: ExecutionMandateContext,
) -> dict[str, object]:
    """Return authority-none mandate evidence for report publication."""
    if context.execution_authority != "none":
        raise ValueError("V58 mandate context has execution authority")
    return dict(context.payload)


def _require_report_only(document: Record) -> None:
    contract = _mapping(document.get("checkpoint_contract"), "checkpoint contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_pause": False,
        "automatic_retuning": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 mandate checkpoint lacks a report-only contract")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 mandate {label} must be an object")
    return value


def _raw_evidence(raw: bytes) -> dict[str, object]:
    return {"sha256": sha256(raw).hexdigest(), "bytes": len(raw)}
