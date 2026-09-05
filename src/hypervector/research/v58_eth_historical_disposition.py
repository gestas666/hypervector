"""Source-bound historical disposition loader for the exact V58 ETH route."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cohort_route_lifecycle_values import count, mapping, text

Record = Mapping[str, object]
Payload = dict[str, object]

_DECISION_KEYS = (
    "disposition",
    "retain_current_native_12h_exit_contract",
    "current_live_lifecycle_changes_decision",
    "live_change_proposed",
)


def load_historical_disposition(
    journal_path: Path,
    *,
    strategy_id: str,
) -> tuple[Payload, Payload]:
    """Load and verify one immutable report-only ETH disposition."""
    journal_reference = file_evidence(journal_path)
    journal = mapping(
        json.loads(journal_path.read_text(encoding="utf-8")),
        "ETH historical disposition",
    )
    _require_identity(journal, strategy_id)
    source = mapping(journal.get("source_artifact"), "ETH historical source")
    source_path = _source_path(source.get("path"))
    source_reference = _declared_file_evidence(source)
    if file_evidence(source_path) != source_reference:
        raise ValueError("V58 ETH historical source artifact changed")
    decision = mapping(journal.get("decision"), "ETH historical decision")
    payload = {key: decision.get(key) for key in _DECISION_KEYS}
    if file_evidence(journal_path) != journal_reference:
        raise ValueError("V58 ETH historical disposition changed")
    return payload, {
        "historical_disposition": {
            "path": str(journal_path.resolve()),
            **journal_reference,
        },
        "historical_source_artifact": {
            "path": str(source_path),
            **source_reference,
        },
    }


def _require_identity(journal: Record, strategy_id: str) -> None:
    contract = mapping(journal.get("contract"), "ETH historical contract")
    expected = {"symbol": "ETH", "strategy_id": strategy_id}
    if any(journal.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 ETH historical disposition identity is invalid")
    if (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
    ):
        raise ValueError("V58 ETH historical disposition has execution authority")
    decision = mapping(journal.get("decision"), "ETH historical decision")
    expected_decision = {
        "disposition": "reject_global_eth_exit_replacement",
        "retain_current_native_12h_exit_contract": True,
        "current_live_lifecycle_changes_decision": False,
        "live_change_proposed": False,
    }
    if any(decision.get(key) != value for key, value in expected_decision.items()):
        raise ValueError("V58 ETH historical decision contract is invalid")


def _declared_file_evidence(value: Record) -> dict[str, object]:
    return {
        "sha256": text(value.get("sha256"), "historical source hash"),
        "bytes": count(value.get("bytes"), "historical source bytes"),
    }


def _source_path(value: object) -> Path:
    path = Path(text(value, "historical source path"))
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[3] / path
