"""Point-in-time duration checkpoints for the pending V58 ETH lifecycle."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.data.jsonl_prefix import read_jsonl_verified_prefix
from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cohort_eligible_exact_depth_forward import (
    build_eligible_exact_depth_forward_report,
)
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvent,
    EligiblePolicyFundingEvidence,
)
from hypervector.research.cohort_observer_exact_books import (
    extract_observer_asset_books,
    select_compatible_report_only_observer_runs,
)

Record = Mapping[str, object]

_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
_CANDIDATE = f"{_STRATEGY}_v55_forward"
_SYMBOL = "ETH"
_SOURCE_HOLD_MINUTES = 720
_DURATIONS = (240, 480)
_MAXIMUM_BOOK_DELAY_MS = 60_000


def load_v58_eth_duration_checkpoint_report(
    status_path: Path,
) -> dict[str, object]:
    """Load one source-bound V58 ETH duration checkpoint report."""
    generator_path = Path(__file__).resolve()
    generator_evidence = file_evidence(generator_path)
    status_evidence = file_evidence(status_path)
    status = _mapping(json.loads(status_path.read_bytes()), "lifecycle status")
    source = _mapping(status.get("source_evidence"), "source evidence")
    ledger = _mapping(source.get("ledger"), "observer ledger evidence")
    ledger_path = Path(_text(ledger.get("path"), "observer ledger path"))
    records = read_jsonl_verified_prefix(
        ledger_path,
        "V58 ETH duration observer ledger",
        length=_positive_int(ledger.get("stable_bytes"), "ledger prefix bytes"),
        expected_sha256=_text(ledger.get("sha256"), "ledger prefix sha256"),
    )
    report = build_v58_eth_duration_checkpoint_report(status, records)
    if file_evidence(status_path) != status_evidence:
        raise ValueError("V58 ETH lifecycle status changed during duration analysis")
    if file_evidence(generator_path) != generator_evidence:
        raise ValueError("V58 ETH duration generator changed during analysis")
    report["generated_at_utc"] = datetime.now(UTC).isoformat()
    report["source_evidence"] = {
        "status": {"path": str(status_path.resolve()), **status_evidence},
        "observer_ledger": dict(ledger),
        "funding": dict(_mapping(source.get("funding"), "funding evidence")),
        "checkpoint_generator": {
            "path": str(generator_path),
            **generator_evidence,
        },
    }
    return report


def build_v58_eth_duration_checkpoint_report(
    status: Record,
    records: Sequence[Record],
) -> dict[str, object]:
    """Compare frozen four- and eight-hour exits for one V58 ETH entry."""
    contract = _source_contract(status)
    attempt = _source_attempt(status, contract)
    selected, identities = select_compatible_report_only_observer_runs(
        records, _text(contract.get("source_run_id"), "source run id")
    )
    _require_identities(contract, identities)
    books = extract_observer_asset_books(selected, (_SYMBOL,))[_SYMBOL]
    funding = _funding_evidence(status)
    checkpoints = {
        f"fixed_{duration}m": _duration_checkpoint(
            selected, books, contract, attempt, funding, duration
        )
        for duration in _DURATIONS
    }
    return {
        "schema_version": 1,
        "mode": "v58_eth_fixed_entry_duration_checkpoint_v1",
        "source_lifecycle": _source_identity(attempt),
        "duration_checkpoints": checkpoints,
        "retained_control": {
            "maximum_hold_minutes": _SOURCE_HOLD_MINUTES,
            "state": status.get("state"),
            "deadline_time_ms": attempt.get("deadline_time_ms"),
        },
        "retained_control_snapshot": _control_snapshot(
            attempt, checkpoints["fixed_480m"]
        ),
        "historical_optimum_claim": False,
        "strategy_change_supported": False,
        "execution_authority": "none",
    }


def _source_contract(status: Record) -> Record:
    expected_status = {
        "schema_version": 1,
        "mode": "cohort_eligible_exact_visible_depth_forward_report",
    }
    if any(status.get(field) != value for field, value in expected_status.items()):
        raise ValueError("V58 ETH duration source contract is invalid")
    contract = _mapping(status.get("contract"), "source contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "actual_orders_or_fills_claimed": False,
        "source_strategy_id": _STRATEGY,
        "candidate_strategy_id": _CANDIDATE,
        "symbol": _SYMBOL,
        "stop_bps": 60.0,
        "notional_usd": 750.0,
        "maximum_hold_minutes": _SOURCE_HOLD_MINUTES,
        "close_on_eligible_opposite_signal": True,
        "same_cycle_reversal": False,
        "taker_fee_rate": 0.00045,
    }
    if any(contract.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH duration source contract is invalid")
    _text(contract.get("source_run_id"), "source run id")
    _text(contract.get("profile_fingerprint"), "profile fingerprint")
    return contract


def _source_attempt(status: Record, contract: Record) -> Record:
    attempts = tuple(
        row
        for row in _records(status.get("latest_attempts"), "source attempts")
        if row.get("status") == "exit_pending"
    )
    if len(attempts) != 1:
        raise ValueError("V58 ETH duration source requires one pending lifecycle")
    attempt = attempts[0]
    expected = {
        "source_run_id": contract.get("source_run_id"),
        "strategy_id": _STRATEGY,
        "candidate_strategy_id": _CANDIDATE,
        "symbol": _SYMBOL,
    }
    if any(attempt.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH duration source lifecycle is invalid")
    if attempt.get("side") not in {"long", "short"}:
        raise ValueError("V58 ETH duration source side is invalid")
    entry = _positive_int(attempt.get("entry_time_ms"), "entry time")
    deadline = _positive_int(attempt.get("deadline_time_ms"), "deadline")
    if deadline != entry + _SOURCE_HOLD_MINUTES * 60_000:
        raise ValueError("V58 ETH duration source deadline is invalid")
    current = attempt.get("current_exit_time_ms", attempt.get("exit_time_ms"))
    if _positive_int(current, "current exit time") < entry + max(_DURATIONS) * 60_000:
        raise ValueError("V58 ETH duration checkpoints have not elapsed")
    return attempt


def _require_identities(contract: Record, identities: Sequence[Record]) -> None:
    run_ids = tuple(_text(row.get("run_id"), "compatible run id") for row in identities)
    expected = _text_list(contract.get("compatible_run_ids"), "compatible run ids")
    if run_ids != expected:
        raise ValueError("V58 ETH duration compatible runs are inconsistent")
    fingerprint = contract.get("profile_fingerprint")
    if any(row.get("profile_fingerprint") != fingerprint for row in identities):
        raise ValueError("V58 ETH duration profile fingerprint is inconsistent")


def _duration_checkpoint(
    records: Sequence[Record],
    books: Sequence[Record],
    contract: Record,
    source_attempt: Record,
    funding: EligiblePolicyFundingEvidence,
    duration: int,
) -> dict[str, object]:
    report = build_eligible_exact_depth_forward_report(
        records,
        books,
        policy_report=_policy_report(contract, duration),
        funding_evidence=funding,
        taker_fee_rate=float(contract["taker_fee_rate"]),
        maximum_entry_delay_ms=_MAXIMUM_BOOK_DELAY_MS,
        maximum_exit_delay_ms=_MAXIMUM_BOOK_DELAY_MS,
    )
    matches = [
        row
        for row in _records(report.get("latest_executions"), "checkpoint executions")
        if row.get("decision_time_ms") == source_attempt.get("decision_time_ms")
        and row.get("entry_time_ms") == source_attempt.get("entry_time_ms")
        and row.get("side") == source_attempt.get("side")
    ]
    if len(matches) != 1:
        raise ValueError(f"V58 ETH fixed-{duration}m checkpoint is unresolved")
    result = dict(matches[0])
    if result.get("net_return_scope") != "exact_depth_fee_and_funding":
        raise ValueError(f"V58 ETH fixed-{duration}m funding is incomplete")
    result["maximum_hold_minutes"] = duration
    return result


def _policy_report(contract: Record, duration: int) -> dict[str, object]:
    return {
        "mode": "cohort_config_bound_eligible_policy_forward_report",
        "contract": {
            **dict(contract),
            "candidate_strategy_id": f"{_STRATEGY}_fixed_{duration}m_checkpoint_v1",
            "maximum_hold_minutes": duration,
            "portfolio_pnl_claimed": False,
            "execution_authority": "none",
        },
    }


def _funding_evidence(status: Record) -> EligiblePolicyFundingEvidence:
    source = _mapping(status.get("source_evidence"), "source evidence")
    funding = _mapping(source.get("funding"), "funding evidence")
    if funding.get("status") != "covered" or funding.get("symbol") != _SYMBOL:
        raise ValueError("V58 ETH duration funding evidence is incomplete")
    events = tuple(
        EligiblePolicyFundingEvent(
            timestamp_ms=_positive_int(row.get("timestamp_ms"), "funding time"),
            funding_rate=_number(row.get("funding_rate"), "funding rate"),
        )
        for row in _records(funding.get("events"), "funding events")
    )
    return EligiblePolicyFundingEvidence(
        symbol=_SYMBOL,
        requested_start_ms=_positive_int(
            funding.get("requested_start_ms"), "funding start"
        ),
        requested_end_ms=_positive_int(funding.get("requested_end_ms"), "funding end"),
        events=events,
    )


def _source_identity(attempt: Record) -> dict[str, object]:
    return {
        field: attempt.get(field)
        for field in (
            "source_run_id",
            "strategy_id",
            "candidate_strategy_id",
            "symbol",
            "side",
            "decision_time_ms",
            "available_time_ms",
            "entry_time_ms",
        )
    }


def _control_snapshot(attempt: Record, fixed_eight_hour: Record) -> dict[str, object]:
    scope = attempt.get("net_return_scope")
    if scope != "exact_depth_fee_and_funding":
        raise ValueError("V58 ETH retained control funding is incomplete")
    snapshot_time = _positive_int(attempt.get("current_exit_time_ms"), "snapshot time")
    return {
        "status": attempt.get("status"),
        "snapshot_time_ms": snapshot_time,
        "current_exit_price": _number(attempt.get("current_exit_price"), "exit price"),
        "current_gross_return_bps": _number(
            attempt.get("current_gross_return_bps"), "gross return"
        ),
        "current_fee_bps": _number(attempt.get("current_fee_bps"), "fee bps"),
        "current_funding_bps": _number(
            attempt.get("current_funding_bps"), "funding bps"
        ),
        "current_net_return_bps": _number(
            attempt.get("current_net_return_bps"), "net return"
        ),
        "current_simulated_net_pnl_usd": _number(
            attempt.get("current_simulated_net_pnl_usd"), "net pnl"
        ),
        "net_return_scope": scope,
        "same_timestamp_as_fixed_480m": snapshot_time
        == fixed_eight_hour.get("exit_time_ms"),
        "actual_exit_fill_claim": False,
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    if not all(isinstance(row, Mapping) for row in value):
        raise ValueError(f"{label} rows must be mappings")
    return tuple(row for row in value if isinstance(row, Mapping))


def _text_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    return tuple(_text(row, label) for row in value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)
