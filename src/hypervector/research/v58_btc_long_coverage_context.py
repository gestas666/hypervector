"""Attach the completed BTC long-coverage disposition to V58 research state."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from math import isfinite
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence

Record = Mapping[str, object]

_ROUTE = "liquidity_sweep_long_1h_stop60_target60_v2|BTC"
_SWEEP_HYPOTHESIS = "V58_BTC_SWEEP_PRIMARY_RELAXATION_CAUSAL_REPLAY_V1"
_TREND_HYPOTHESIS = "V58_BTC_15M_TREND_PULLBACK_REACCELERATION_LONG_V1"


@dataclass(frozen=True)
class _ResultContract:
    hypothesis_id: str
    rejected_change: str
    evidence_labels: tuple[str, ...]
    required_supersedes: tuple[str, ...] = ()


_RESULT_CONTRACTS = {
    _SWEEP_HYPOTHESIS: _ResultContract(
        hypothesis_id=_SWEEP_HYPOTHESIS,
        rejected_change="remove_downside_sweep_predicate_only",
        evidence_labels=("preregistration", "report", "trade_sidecar"),
    ),
    _TREND_HYPOTHESIS: _ResultContract(
        hypothesis_id=_TREND_HYPOTHESIS,
        rejected_change="add_trend_pullback_reacceleration_long",
        evidence_labels=(
            "preregistration",
            "report",
            "trade_sidecar",
            "previous_result",
        ),
        required_supersedes=(_SWEEP_HYPOTHESIS,),
    ),
}


def attach_v58_btc_long_coverage_result(
    report: dict[str, object],
    path: Path,
    *,
    project_root: Path | None = None,
) -> None:
    """Attach one source-verified rejected challenger without live authority."""
    _require_report_only(report)
    if not path.is_file():
        report["btc_long_coverage_context"] = _unavailable_payload()
        return
    root = project_root or Path.cwd()
    before = file_evidence(path)
    artifact = _load_json(path)
    context = _context_payload(artifact, root)
    if file_evidence(path) != before:
        raise ValueError("V58 BTC long-coverage result changed during analysis")
    report["btc_long_coverage_context"] = context
    _attach_to_ledger(report, context)
    evidence = _mutable_mapping(report.get("evidence"), "report evidence")
    evidence["btc_long_coverage_context"] = {
        "path": str(path.resolve()),
        **before,
    }


def _unavailable_payload() -> dict[str, object]:
    return {
        "status": "not_available",
        "reason": "btc_long_coverage_result_not_published",
        "execution_authority": "none",
        "live_change_supported": False,
    }


def _context_payload(artifact: Record, project_root: Path) -> dict[str, object]:
    contract = _require_result_contract(artifact)
    chronological = _mapping(artifact.get("chronological_results"), "chronology")
    validation = _partition_metrics(chronological, "validation")
    holdout = _partition_metrics(chronological, "pseudo_holdout")
    evidence = _verified_evidence(artifact, project_root, contract)
    rejected_ids = [*contract.required_supersedes, contract.hypothesis_id]
    context: dict[str, object] = {
        "status": "rejected",
        "hypothesis_id": contract.hypothesis_id,
        "active_route": _ROUTE,
        "rejected_change": contract.rejected_change,
        "live_control_action": "retain_unchanged",
        "validation_nominal_candidate_net_pnl_usd": validation["candidate"],
        "validation_nominal_control_net_pnl_usd": validation["control"],
        "pseudo_holdout_nominal_candidate_net_pnl_usd": holdout["candidate"],
        "pseudo_holdout_nominal_control_net_pnl_usd": holdout["control"],
        "source_evidence": evidence,
        "rejected_challenger_ids": rejected_ids,
        "execution_authority": "none",
        "live_change_supported": False,
        "automatic_live_change": False,
    }
    if contract.hypothesis_id == _TREND_HYPOTHESIS:
        context.update(_trend_route_metrics(chronological))
    return context


def _require_result_contract(artifact: Record) -> _ResultContract:
    expected = {
        "schema_version": "cohort_strategy_result_v1",
        "status": "rejected",
    }
    if any(artifact.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 BTC long-coverage result identity is invalid")
    hypothesis_id = _text(artifact.get("hypothesis_id"), "hypothesis identity")
    contract = _RESULT_CONTRACTS.get(hypothesis_id)
    if contract is None:
        raise ValueError("V58 BTC long-coverage result identity is invalid")
    supersedes = _text_sequence(artifact.get("supersedes", ()), "supersedes")
    if supersedes != contract.required_supersedes:
        raise ValueError("V58 BTC long-coverage supersession is invalid")
    authority = _mapping(artifact.get("authority"), "result authority")
    required_authority = {
        "report_only": True,
        "execution_authority": "none",
        "live_configuration_changed": False,
        "live_process_changed": False,
        "automatic_promotion": False,
        "retuning_authorized": False,
    }
    if any(authority.get(key) != value for key, value in required_authority.items()):
        raise ValueError("V58 BTC long-coverage result authority is invalid")
    _require_rejection(_mapping(artifact.get("decision"), "result decision"))
    return contract


def _require_rejection(decision: Record) -> None:
    expected = {
        "accepted_for_next_validation_stage": False,
        "disposition": "reject_frozen_candidate",
        "retain_live_control_unchanged": True,
        "nearby_retuning_allowed": False,
        "live_change_recommended": False,
    }
    if any(decision.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 BTC long-coverage rejection is invalid")


def _partition_metrics(chronological: Record, partition: str) -> dict[str, float]:
    row = _mapping(chronological.get(partition), f"{partition} result")
    candidate = _mapping(row.get("nominal_candidate"), f"{partition} candidate")
    control = _mapping(row.get("nominal_control"), f"{partition} control")
    candidate_net = _number(candidate.get("net_pnl_usd"), "candidate net PnL")
    control_net = _number(control.get("net_pnl_usd"), "control net PnL")
    if candidate_net >= 0.0 or control_net <= 0.0:
        raise ValueError("V58 BTC long-coverage disposition economics are inconsistent")
    return {"candidate": candidate_net, "control": control_net}


def _trend_route_metrics(chronological: Record) -> dict[str, float]:
    validation = _shared_incremental(chronological, "validation")
    holdout = _shared_incremental(chronological, "pseudo_holdout")
    return {
        "validation_current_v58_incremental_net_pnl_usd": validation,
        "pseudo_holdout_current_v58_incremental_net_pnl_usd": holdout,
    }


def _shared_incremental(chronological: Record, partition: str) -> float:
    row = _mapping(chronological.get(partition), f"{partition} result")
    result = _number(
        row.get("shared_current_v58_nominal_incremental_net_pnl_usd"),
        f"{partition} shared V58 incremental net PnL",
    )
    if result >= 0.0:
        raise ValueError("V58 BTC long-coverage route economics are inconsistent")
    return result


def _verified_evidence(
    artifact: Record,
    project_root: Path,
    contract: _ResultContract,
) -> dict[str, dict[str, object]]:
    rows = _mapping(artifact.get("evidence"), "result evidence")
    output: dict[str, dict[str, object]] = {}
    for label in contract.evidence_labels:
        row = _mapping(rows.get(label), f"{label} evidence")
        raw_path = _text(row.get("path"), f"{label} path")
        source = Path(raw_path)
        resolved = source if source.is_absolute() else project_root / source
        expected = {
            "sha256": _sha256(row.get("sha256"), f"{label} hash"),
            "bytes": _positive_integer(row.get("bytes"), f"{label} bytes"),
        }
        if not resolved.is_file() or file_evidence(resolved) != expected:
            raise ValueError(f"V58 BTC long-coverage {label} evidence changed")
        output[label] = {"path": str(resolved.resolve()), **expected}
    return output


def _attach_to_ledger(
    report: dict[str, object],
    context: dict[str, object],
) -> None:
    ledger = _sequence(report.get("hypothesis_ledger"), "hypothesis ledger")
    matches = [row for row in ledger if row.get("route") == _ROUTE]
    if len(matches) != 1 or not isinstance(matches[0], dict):
        raise ValueError("V58 BTC long-coverage hypothesis identity is invalid")
    row = matches[0]
    if "long_coverage_challenger" in row:
        raise ValueError("V58 BTC long-coverage challenger is already attached")
    row["long_coverage_challenger"] = context
    rejected = context.get("rejected_challenger_ids")
    row["rejected_challenger_ids"] = list(
        _text_sequence(rejected, "rejected challenger identities")
    )


def _require_report_only(report: Record) -> None:
    contract = _mapping(report.get("contract"), "report contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 BTC long-coverage report authority is invalid")


def _load_json(path: Path) -> Record:
    try:
        value: object = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"V58 BTC long-coverage result is unreadable: {path}"
        ) from error
    return _mapping(value, "BTC long-coverage result")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 BTC long-coverage {label} must be a mapping")
    return value


def _mutable_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"V58 BTC long-coverage {label} must be mutable")
    return value


def _sequence(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"V58 BTC long-coverage {label} must be an array")
    if any(not isinstance(row, Mapping) for row in value):
        raise ValueError(f"V58 BTC long-coverage {label} rows must be mappings")
    return tuple(row for row in value if isinstance(row, Mapping))


def _text_sequence(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"V58 BTC long-coverage {label} must be an array")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"V58 BTC long-coverage {label} must contain text")
    return tuple(item for item in value if isinstance(item, str))


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 BTC long-coverage {label} must be numeric")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"V58 BTC long-coverage {label} must be finite")
    return result


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"V58 BTC long-coverage {label} must be text")
    return value


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"V58 BTC long-coverage {label} must be positive integer")
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ValueError(f"V58 BTC long-coverage {label} must be SHA-256")
    return text
