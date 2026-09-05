"""Causal, report-only profit-lock context for the current V58 ETH path."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from hypervector.data.jsonl_prefix import read_jsonl_verified_prefix
from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cohort_policy_forward_profit_lock import (
    build_policy_forward_profit_lock_report,
)
from hypervector.research.cohort_trade_reflection_index import (
    build_reflection_evidence_index,
)
from hypervector.research.v58_eth_censored_context import select_eth_lifecycle_scope
from hypervector.research.v58_eth_exit_research_context import EthExitResearchContext

Record = Mapping[str, object]

_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
_CANDIDATE = f"{_STRATEGY}_v55_forward"
_HISTORICAL_IDS = (
    "profit_a25_floor15_trail10",
    "profit_a40_floor15_trail20",
    "profit_a60_floor15_trail30",
)
_POLICY_IDS = tuple(value.removeprefix("profit_") for value in _HISTORICAL_IDS)


@dataclass(frozen=True)
class EthProfitLockContext:
    """Execution-incapable state of historically rejected ETH exit locks."""

    payload: dict[str, object]
    evidence: dict[str, object]
    execution_authority: str = "none"


def load_v58_eth_profit_lock_context(
    status_path: Path,
    history: EthExitResearchContext,
) -> EthProfitLockContext:
    """Evaluate rejected locks on one exact, frozen observer-ledger prefix."""
    _require_history(history)
    raw = status_path.read_bytes()
    status_evidence = {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}
    status = _mapping(json.loads(raw), "ETH lifecycle status")
    contract, attempt, state = _status_contract(status)
    ledger = _ledger_evidence(status)
    records = _compatible_records(_verified_records(ledger), contract)
    if attempt is None:
        payload = _awaiting_payload()
    elif state == "technically_censored":
        payload = _censored_payload(attempt)
    else:
        candles = build_reflection_evidence_index(records).candles.get("ETH", {})
        report = build_policy_forward_profit_lock_report(
            candles,
            {"latest_attempts": [attempt]},
            taker_fee_rate=_number(contract.get("taker_fee_rate"), "taker fee rate"),
        )
        payload = _payload(report, state)
    if file_evidence(status_path) != status_evidence:
        raise ValueError("V58 ETH lifecycle status changed during lock evaluation")
    return EthProfitLockContext(
        payload,
        {
            "status": {"path": str(status_path.resolve()), **status_evidence},
            "observer_ledger": dict(ledger),
            "historical_disposition": dict(history.evidence),
        },
    )


def eth_profit_lock_context_payload(
    context: EthProfitLockContext,
) -> dict[str, object]:
    """Serialize provisional lock evidence without reopening an exit policy."""
    return {
        **context.payload,
        "counterfactual_is_live_fill": False,
        "performance_gate": False,
        "automatic_policy_reopening": False,
        "strategy_change_supported": False,
        "execution_authority": context.execution_authority,
    }


def _status_contract(
    status: Record,
) -> tuple[Record, dict[str, object] | None, str]:
    expected = {
        "schema_version": 1,
        "mode": "cohort_eligible_exact_visible_depth_forward_report",
    }
    if any(status.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH profit-lock source contract is invalid")
    contract = _mapping(status.get("contract"), "ETH lifecycle contract")
    identity = _mapping(status.get("identity"), "ETH lifecycle identity")
    _require_identity(contract, identity)
    summary = _mapping(status.get("summary"), "ETH lifecycle summary")
    attempts = _records(status.get("latest_attempts"), "ETH attempts")
    executions = _records(status.get("latest_executions"), "ETH executions")
    scope = select_eth_lifecycle_scope(
        summary, attempts, executions, contract, status.get("state")
    )
    state = (
        "technically_censored"
        if scope.current_state == "censored"
        else scope.current_state
    )
    attempt = None if scope.current is None else dict(scope.current)
    if state == "resolved" and attempt is not None:
        attempt = _current_aliases(attempt)
    return contract, attempt, state


def _require_identity(contract: Record, identity: Record) -> None:
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "source_strategy_id": _STRATEGY,
        "candidate_strategy_id": _CANDIDATE,
        "symbol": "ETH",
        "taker_fee_rate": 0.00045,
    }
    if any(contract.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH profit-lock authority or identity is invalid")
    run_ids = _text_list(contract.get("compatible_run_ids"), "compatible run ids")
    if identity.get("source_run_id") not in run_ids or identity.get(
        "profile_fingerprint"
    ) != contract.get("profile_fingerprint"):
        raise ValueError("V58 ETH profit-lock observer identity is invalid")


def _compatible_records(
    records: Sequence[Record], contract: Record
) -> tuple[Record, ...]:
    run_ids = set(_text_list(contract.get("compatible_run_ids"), "compatible run ids"))
    profile = contract.get("profile_fingerprint")
    selected = tuple(row for row in records if row.get("run_id") in run_ids)
    if not selected or any(
        row.get("profile_fingerprint") != profile
        or row.get("execution_authority") != "none"
        for row in selected
    ):
        raise ValueError("V58 ETH profit-lock ledger identity is invalid")
    return selected


def _payload(report: Record, state: str) -> dict[str, object]:
    results = _records(report.get("latest_results"), "ETH profit-lock results")
    if len(results) != 1:
        raise ValueError("V58 ETH profit-lock result count is invalid")
    result = results[0]
    policies = _mapping(result.get("policies"), "ETH profit-lock policies")
    if set(policies) != set(_POLICY_IDS):
        raise ValueError("V58 ETH profit-lock policy identity changed")
    return {
        "route": f"{_STRATEGY}|ETH",
        "lifecycle_state": state,
        "historical_disposition": "rejected_in_both_source_partitions",
        "historically_rejected_policy_ids": list(_HISTORICAL_IDS),
        "completed_bars_expected": result.get("completed_bars_expected"),
        "completed_bars_observed": result.get("completed_bars_observed"),
        "current_exact_net_excluding_funding_bps": result.get(
            "current_exact_net_excluding_funding_bps"
        ),
        "policies": dict(policies),
        "interpretation": (
            "one path updates diagnostics only; it does not overturn the frozen "
            "two-partition rejection"
        ),
    }


def _censored_payload(attempt: Record) -> dict[str, object]:
    maximum = _positive_integer(
        attempt.get("maximum_active_book_gap_ms"), "ETH maximum book gap"
    )
    allowed = _positive_integer(
        attempt.get("maximum_allowed_active_book_gap_ms"), "ETH allowed book gap"
    )
    if maximum <= allowed:
        raise ValueError("V58 ETH censored profit-lock gap is inconsistent")
    return {
        "route": f"{_STRATEGY}|ETH",
        "lifecycle_state": "technically_censored",
        "evaluation_status": "unavailable_active_book_path_gap",
        "historical_disposition": "rejected_in_both_source_partitions",
        "historically_rejected_policy_ids": list(_HISTORICAL_IDS),
        "maximum_active_book_gap_ms": maximum,
        "maximum_allowed_active_book_gap_ms": allowed,
        "policies": {},
        "interpretation": "counterfactual withheld because active path is incomplete",
    }


def _awaiting_payload() -> dict[str, object]:
    return {
        "route": f"{_STRATEGY}|ETH",
        "lifecycle_state": "awaiting_first_lifecycle",
        "evaluation_status": "unavailable_no_current_lifecycle",
        "historical_disposition": "rejected_in_both_source_partitions",
        "historically_rejected_policy_ids": list(_HISTORICAL_IDS),
        "policies": {},
        "interpretation": "counterfactual withheld until a current lifecycle exists",
    }


def _require_history(history: EthExitResearchContext) -> None:
    rejected = history.payload.get("rejected_profit_locks")
    if history.execution_authority != "none" or rejected != list(_HISTORICAL_IDS):
        raise ValueError("V58 ETH historical policy set or authority is invalid")


def _current_aliases(execution: Record) -> dict[str, object]:
    output = dict(execution)
    for suffix in (
        "exit_time_ms",
        "exit_price",
        "gross_return_bps",
        "fee_bps",
        "funding_bps",
        "net_return_bps",
    ):
        output[f"current_{suffix}"] = execution.get(suffix)
    return output


def _ledger_evidence(status: Record) -> Record:
    source = _mapping(status.get("source_evidence"), "ETH source evidence")
    return _mapping(source.get("ledger"), "ETH ledger evidence")


def _verified_records(ledger: Record) -> tuple[dict[str, object], ...]:
    return read_jsonl_verified_prefix(
        Path(_text(ledger.get("path"), "ETH ledger path")),
        "V58 ETH profit-lock ledger",
        length=_positive_integer(ledger.get("stable_bytes"), "ETH ledger bytes"),
        expected_sha256=_text(ledger.get("sha256"), "ETH ledger SHA-256"),
    )


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list):
        raise ValueError(f"V58 {label} must be an array")
    return tuple(_mapping(row, label) for row in value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 {label} must be an object")
    return value


def _text_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"V58 {label} must be a non-empty array")
    output = tuple(_text(row, label) for row in value)
    if len(output) != len(set(output)):
        raise ValueError(f"V58 {label} must be unique")
    return output


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"V58 {label} must be non-empty text")
    return value.strip()


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 {label} must be numeric")
    return float(value)


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"V58 {label} must be a positive integer")
    return value
