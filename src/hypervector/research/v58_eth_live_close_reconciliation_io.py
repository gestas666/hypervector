"""Immutable input loading for the first V58 ETH live-close report."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

from hypervector.data.jsonl_prefix import (
    read_jsonl_prefix,
    read_jsonl_verified_prefix,
    require_jsonl_prefix_unchanged,
)
from hypervector.data.oxa_storage import file_evidence
from hypervector.research.hip3_development_provenance import require_unchanged_file
from hypervector.research.v58_eth_live_close_reconciliation import (
    build_v58_eth_live_close_reconciliation,
)

Record = Mapping[str, object]

_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
_OBSERVER_RUN = "bidirectional-observe-1787127644202"
_COMPARISON_KEYS = ("native_exit_disposition", "component_decay_result")


@dataclass(frozen=True)
class _CloseInputs:
    preregistration: Record
    live_rows: tuple[dict[str, object], ...]
    continuous: Record
    venue: Record
    observer_resolution: Record
    observer_provenance: dict[str, object]
    evidence: dict[str, object]


def load_v58_eth_live_close_reconciliation(
    preregistration_path: Path,
    *,
    expected_preregistration_sha256: str,
    continuous_path: Path,
    venue_path: Path,
    observer_status_path: Path,
    observer_provenance_path: Path,
    expected_observer_provenance_sha256: str,
    generated_at: datetime,
) -> dict[str, object]:
    """Load authenticated append-only evidence and build one close report."""
    inputs = _load_inputs(
        preregistration_path,
        expected_preregistration_sha256,
        continuous_path,
        venue_path,
        observer_status_path,
        observer_provenance_path,
        expected_observer_provenance_sha256,
    )
    _require_report_only(inputs.continuous, "continuous report")
    report = build_v58_eth_live_close_reconciliation(
        inputs.preregistration,
        _mapping(
            inputs.continuous.get("eth_risk_normalized_lock_context"),
            "closed context",
        ),
        inputs.live_rows,
        inputs.venue,
        inputs.observer_resolution,
    )
    _recheck_inputs(inputs.evidence)
    report["generated_at_utc"] = _aware_utc(generated_at).isoformat()
    report["observer_window_provenance"] = inputs.observer_provenance
    report["source_evidence"] = inputs.evidence
    return report


def _load_inputs(
    preregistration_path: Path,
    expected_preregistration_sha256: str,
    continuous_path: Path,
    venue_path: Path,
    observer_status_path: Path,
    observer_provenance_path: Path,
    expected_observer_provenance_sha256: str,
) -> _CloseInputs:
    prereg, prereg_evidence = _load_preregistration(
        preregistration_path, expected_preregistration_sha256
    )
    sources = _mapping(prereg.get("source_prefixes"), "source prefixes")
    live_rows, live_evidence, observer_evidence = _load_close_ledgers(sources)
    static_evidence = _verify_static_sources(sources)
    comparison_evidence = _verify_comparison_sources(
        _mapping(prereg.get("comparison_evidence"), "comparison evidence")
    )
    continuous, continuous_evidence = _load_json(continuous_path, "continuous report")
    venue, venue_evidence = _load_json(venue_path, "venue preflight")
    status, status_evidence = _load_json(observer_status_path, "observer status")
    provenance, provenance_evidence = _load_observer_provenance(
        observer_provenance_path, expected_observer_provenance_sha256
    )
    evidence = _source_evidence(
        preregistration_path,
        prereg_evidence,
        continuous_path,
        continuous_evidence,
        venue_path,
        venue_evidence,
        observer_status_path,
        status_evidence,
        observer_provenance_path,
        provenance_evidence,
        live_evidence,
        observer_evidence,
        static_evidence,
        comparison_evidence,
    )
    return _CloseInputs(
        preregistration=prereg,
        live_rows=live_rows,
        continuous=continuous,
        venue=venue,
        observer_resolution=_observer_resolution(status),
        observer_provenance=provenance,
        evidence=evidence,
    )


def _load_close_ledgers(
    sources: Record,
) -> tuple[tuple[dict[str, object], ...], dict[str, object], dict[str, object]]:
    live_rows, live_evidence = _load_ledger_source(
        _mapping(sources.get("live_eth_ledger"), "live ETH source"),
        "V58 live ETH ledger",
    )
    _, observer_evidence = _load_ledger_source(
        _mapping(sources.get("prospective_observer_ledger"), "observer source"),
        "V58 prospective observer ledger",
    )
    return live_rows, live_evidence, observer_evidence


def _source_evidence(
    preregistration_path: Path,
    preregistration: Record,
    continuous_path: Path,
    continuous: Record,
    venue_path: Path,
    venue: Record,
    observer_path: Path,
    observer: Record,
    provenance_path: Path,
    provenance: Record,
    live: Record,
    observer_ledger: Record,
    static: Record,
    comparison: Record,
) -> dict[str, object]:
    return {
        "preregistration": {
            "path": str(preregistration_path.resolve()),
            **preregistration,
        },
        "continuous_report": {
            "path": str(continuous_path.resolve()),
            **continuous,
        },
        "venue_preflight": {"path": str(venue_path.resolve()), **venue},
        "observer_status": {
            "path": str(observer_path.resolve()),
            **observer,
        },
        "observer_window_provenance": {
            "path": str(provenance_path.resolve()),
            **provenance,
        },
        "live_eth_ledger": live,
        "prospective_observer_ledger": observer_ledger,
        "comparison_evidence": dict(comparison),
        **static,
    }


def _load_preregistration(
    path: Path, expected_sha256: str
) -> tuple[Record, dict[str, object]]:
    expected = _sha256_text(expected_sha256, "preregistration sha256")
    evidence = file_evidence(path)
    if evidence.get("sha256") != expected:
        raise ValueError("V58 ETH close preregistration hash differs")
    payload = _mapping(json.loads(path.read_bytes()), "preregistration")
    return payload, evidence


def _load_ledger_source(
    source: Record, label: str
) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
    path = Path(_text(source.get("path"), f"{label} path"))
    length = _positive_int(source.get("prefix_bytes"), f"{label} frozen bytes")
    expected = _sha256_text(source.get("prefix_sha256"), f"{label} frozen sha256")
    read_jsonl_verified_prefix(path, label, length=length, expected_sha256=expected)
    rows, evidence = read_jsonl_prefix(path, label)
    output = {
        **evidence,
        "frozen_prefix_bytes": length,
        "frozen_prefix_sha256": expected,
        "frozen_prefix_verified": True,
    }
    return rows, output


def _verify_static_sources(sources: Record) -> dict[str, object]:
    output: dict[str, object] = {}
    for key in ("config", "prestart_manifest"):
        declared = _mapping(sources.get(key), key)
        path = Path(_text(declared.get("path"), f"{key} path"))
        current = file_evidence(path)
        expected_sha = _sha256_text(declared.get("sha256"), f"{key} sha256")
        bytes_differ = "bytes" in declared and current.get("bytes") != declared.get(
            "bytes"
        )
        if current.get("sha256") != expected_sha or bytes_differ:
            raise ValueError(f"V58 ETH close {key} changed after preregistration")
        output[key] = {"path": str(path.resolve()), **current}
    return output


def _verify_comparison_sources(comparison: Record) -> dict[str, object]:
    if set(comparison) != set(_COMPARISON_KEYS):
        raise ValueError("V58 ETH close comparison evidence keys differ")
    output: dict[str, object] = {}
    for key in _COMPARISON_KEYS:
        declared = _mapping(comparison.get(key), f"{key} comparison evidence")
        path = Path(_text(declared.get("path"), f"{key} comparison path"))
        current = file_evidence(path)
        expected = {
            "bytes": _positive_int(declared.get("bytes"), f"{key} comparison bytes"),
            "sha256": _sha256_text(declared.get("sha256"), f"{key} comparison sha256"),
        }
        if current != expected:
            raise ValueError(f"V58 ETH close comparison evidence changed: {key}")
        output[key] = {"path": str(path.resolve()), **current}
    return output


def _load_json(path: Path, label: str) -> tuple[Record, dict[str, object]]:
    evidence = file_evidence(path)
    raw = path.read_bytes()
    if _raw_evidence(raw) != evidence:
        raise ValueError(f"V58 ETH close {label} changed while reading")
    return _mapping(json.loads(raw), label), evidence


def _load_observer_provenance(
    path: Path, expected_sha256: str
) -> tuple[dict[str, object], dict[str, object]]:
    payload, evidence = _load_json(path, "observer window provenance")
    if evidence.get("sha256") != _sha256_text(
        expected_sha256, "observer provenance sha256"
    ):
        raise ValueError("V58 ETH close observer provenance hash differs")
    _require_observer_provenance_contract(payload)
    technical = _mapping(payload.get("technical_reclassification"), "technical")
    continuity = _mapping(payload.get("implementation_continuity"), "continuity")
    scope = _mapping(payload.get("claim_scope"), "claim scope")
    output = {
        "source_run_id": _mapping(payload.get("observer_run"), "observer run")[
            "run_id"
        ],
        "aggregate_window_technical_complete": technical["complete"],
        "technical_gaps": list(_text_sequence(technical.get("technical_gaps"))),
        "maximum_heartbeat_gap_seconds": _positive_number(
            technical.get("maximum_heartbeat_gap_seconds"), "maximum heartbeat gap"
        ),
        "minimum_entry_delay_seconds": _positive_number(
            technical.get("minimum_entry_delay_seconds"), "minimum entry delay"
        ),
        "single_implementation_window": continuity["single_implementation_window"],
        "aggregate_profitability_claim_supported": scope[
            "aggregate_profitability_claim_supported"
        ],
        "exact_lifecycle_comparison_supported": scope[
            "exact_lifecycle_comparison_supported"
        ],
    }
    return output, evidence


def _require_observer_provenance_contract(payload: Record) -> None:
    if payload.get("schema_version") != 1 or payload.get("status") != (
        "aggregate_window_invalid_exact_lifecycle_separately_attributable"
    ):
        raise ValueError("V58 ETH close observer provenance contract differs")
    authority = _mapping(payload.get("authority"), "observer provenance authority")
    expected_authority = {
        "report_only": True,
        "execution_authority": "none",
        "live_configuration_changed": False,
        "runtime_strategy_changed": False,
        "automatic_promotion": False,
    }
    if any(authority.get(key) != value for key, value in expected_authority.items()):
        raise ValueError("V58 ETH close observer provenance authority differs")
    run = _mapping(payload.get("observer_run"), "observer provenance run")
    if run.get("run_id") != _OBSERVER_RUN:
        raise ValueError("V58 ETH close observer provenance run differs")
    technical = _mapping(payload.get("technical_reclassification"), "technical")
    continuity = _mapping(payload.get("implementation_continuity"), "continuity")
    scope = _mapping(payload.get("claim_scope"), "claim scope")
    expected = (
        technical.get("complete") is False
        and _text_sequence(technical.get("technical_gaps"))
        == ("observer_heartbeat_gap_exceeds_entry_delay",)
        and continuity.get("single_implementation_window") is False
        and scope.get("aggregate_profitability_claim_supported") is False
        and scope.get("exact_lifecycle_comparison_supported") is True
    )
    if not expected:
        raise ValueError("V58 ETH close observer provenance disposition differs")


def _observer_resolution(status: Record) -> Record:
    contract = _mapping(status.get("contract"), "observer contract")
    required = {
        "report_only": True,
        "execution_authority": "none",
        "actual_orders_or_fills_claimed": False,
    }
    if any(contract.get(key) != value for key, value in required.items()):
        raise ValueError("V58 ETH close observer contract differs")
    matches = [
        row
        for row in _records(status.get("latest_executions"), "observer executions")
        if row.get("source_run_id") == _OBSERVER_RUN
        and row.get("strategy_id") == _STRATEGY
        and row.get("symbol") == "ETH"
        and row.get("decision_time_ms") == 1787172900000
    ]
    if len(matches) != 1 or matches[0].get("status") != "resolved":
        raise ValueError("V58 ETH close observer comparison is unresolved")
    return matches[0]


def _require_report_only(payload: Record, label: str) -> None:
    contract = _mapping(payload.get("contract"), f"{label} contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "performance_gate": False,
        "runtime_strategy_changed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError(f"V58 ETH close {label} is not report-only")


def _recheck_inputs(evidence: Record) -> None:
    file_keys = (
        "preregistration",
        "continuous_report",
        "venue_preflight",
        "observer_status",
        "observer_window_provenance",
        "config",
        "prestart_manifest",
    )
    for key in file_keys:
        row = _mapping(evidence.get(key), key)
        path = Path(_text(row.get("path"), f"{key} path"))
        require_unchanged_file(path, row)
    comparisons = _mapping(evidence.get("comparison_evidence"), "comparison evidence")
    for key in _COMPARISON_KEYS:
        row = _mapping(comparisons.get(key), f"{key} comparison evidence")
        path = Path(_text(row.get("path"), f"{key} comparison path"))
        require_unchanged_file(path, row)
    _recheck_ledger(
        _mapping(evidence.get("live_eth_ledger"), "live ETH ledger"),
        "V58 live ETH ledger",
    )
    _recheck_ledger(
        _mapping(evidence.get("prospective_observer_ledger"), "observer ledger"),
        "V58 prospective observer ledger",
    )


def _recheck_ledger(evidence: Record, label: str) -> None:
    path = Path(_text(evidence.get("path"), f"{label} path"))
    require_jsonl_prefix_unchanged(path, evidence, label)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("V58 ETH close generation time must be timezone-aware")
    return value.astimezone(UTC)


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"V58 ETH close {label} must be a list")
    return tuple(_mapping(row, label) for row in value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 ETH close {label} must be a mapping")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"V58 ETH close {label} must be non-empty text")
    return value


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"V58 ETH close {label} must be a positive integer")
    return value


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 ETH close {label} must be numeric")
    output = float(value)
    if not output > 0.0:
        raise ValueError(f"V58 ETH close {label} must be positive")
    return output


def _text_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("V58 ETH close observer technical gaps must be a list")
    return tuple(_text(row, "observer technical gap") for row in value)


def _sha256_text(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ValueError(f"V58 ETH close {label} must be lowercase sha256")
    return text


def _raw_evidence(raw: bytes) -> dict[str, object]:
    return {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}
