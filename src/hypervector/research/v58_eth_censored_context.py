"""Fail-closed context for one technically censored V58 ETH lifecycle."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.research.cohort_route_lifecycle_values import mapping, records

Record = Mapping[str, object]

_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
_CANDIDATE = f"{_STRATEGY}_v55_forward"


@dataclass(frozen=True)
class EthLifecycleScope:
    """Validated current-run ETH lifecycles and latest active context."""

    current: Record | None
    current_state: str
    exit_reason: str | None
    lifecycles: tuple[tuple[Record, str], ...]


def current_eth_lifecycle_complete(report: Record, summary: Record) -> bool:
    """Return whether the latest validated ETH lifecycle has a complete path."""
    contract = mapping(report.get("contract"), "ETH lifecycle contract")
    attempts = records(report.get("latest_attempts"), "ETH attempts")
    executions = records(report.get("latest_executions"), "ETH executions")
    scope = select_eth_lifecycle_scope(
        summary, attempts, executions, contract, report.get("state")
    )
    return scope.current_state in {"open", "resolved"}


def censored_eth_lifecycle(
    summary: Record,
    attempts: Sequence[Record],
    executions: Sequence[Record],
    contract: Record,
) -> Record:
    """Validate and return one active-path-censored ETH attempt."""
    counts = {"pending": 0, "resolved": 0, "technical_incomplete": 1}
    if any(summary.get(field) != value for field, value in counts.items()):
        raise ValueError("V58 ETH censored lifecycle counts are inconsistent")
    if len(attempts) != 1 or executions:
        raise ValueError("V58 ETH path requires one censored attempt and no execution")
    attempt = attempts[0]
    validate_censored_eth_attempt(attempt, contract)
    return attempt


def select_eth_lifecycle_scope(
    summary: Record,
    attempts: Sequence[Record],
    executions: Sequence[Record],
    contract: Record,
    report_state: object,
) -> EthLifecycleScope:
    """Reconcile all current-run attempts and select the latest lifecycle."""
    _require_summary(summary, attempts, executions)
    execution_by_decision = _execution_index(executions)
    lifecycles = tuple(
        _lifecycle_row(attempt, execution_by_decision, contract) for attempt in attempts
    )
    consumed = {
        row.get("decision_time_ms") for row, state in lifecycles if state == "resolved"
    }
    if consumed != set(execution_by_decision):
        raise ValueError("V58 ETH resolved lifecycle mapping is incomplete")
    expected_state = (
        "descriptive_exact_depth_evidence" if executions else "awaiting_resolution"
    )
    if report_state != expected_state:
        raise ValueError("V58 ETH aggregate lifecycle state is inconsistent")
    if not lifecycles:
        return EthLifecycleScope(None, "awaiting_first_lifecycle", None, ())
    current, state = max(
        lifecycles,
        key=lambda row: _positive_integer(
            row[0].get("decision_time_ms"), "decision time"
        ),
    )
    reason = current.get("exit_reason") if state == "resolved" else None
    if reason is not None and (not isinstance(reason, str) or not reason.strip()):
        raise ValueError("V58 ETH resolved exit reason is invalid")
    return EthLifecycleScope(current, state, reason, lifecycles)


def awaiting_eth_path_payload() -> dict[str, object]:
    """Serialize a valid quiet current run without inventing path evidence."""
    return {
        "state": "awaiting_first_lifecycle",
        "exit_reason": None,
        "evaluation_status": "unavailable_no_current_lifecycle",
        "route": f"{_STRATEGY}|ETH",
    }


def validate_censored_eth_attempt(attempt: Record, contract: Record) -> None:
    """Validate one active-book-gap attempt without assigning economics."""
    _require_identity(attempt, contract)
    _require_gap(attempt)


def _require_summary(
    summary: Record, attempts: Sequence[Record], executions: Sequence[Record]
) -> None:
    statuses = [row.get("status") for row in attempts]
    expected = {
        "selected_non_overlapping": len(attempts),
        "pending": statuses.count("exit_pending"),
        "resolved": len(executions),
        "technical_incomplete": sum(
            status not in {"exit_pending", "resolved"} for status in statuses
        ),
    }
    if any(summary.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH lifecycle summary is inconsistent")


def _execution_index(executions: Sequence[Record]) -> dict[object, Record]:
    output = {row.get("decision_time_ms"): row for row in executions}
    if len(output) != len(executions) or None in output:
        raise ValueError("V58 ETH resolved lifecycle identities are not unique")
    return output


def _lifecycle_row(
    attempt: Record, executions: Mapping[object, Record], contract: Record
) -> tuple[Record, str]:
    status = attempt.get("status")
    if status == "active_book_path_gap":
        validate_censored_eth_attempt(attempt, contract)
        return attempt, "censored"
    if status == "exit_pending":
        return attempt, "open"
    if status == "resolved":
        decision = attempt.get("decision_time_ms")
        execution = executions.get(decision)
        if execution is None:
            raise ValueError("V58 ETH resolved attempt lacks execution evidence")
        return execution, "resolved"
    raise ValueError("V58 ETH technical lifecycle status is unsupported")


def censored_eth_path_payload(lifecycle: Record, contract: Record) -> dict[str, object]:
    """Serialize censored path evidence without sampled economics."""
    fields = (
        "active_book_gap_start_ms",
        "active_book_gap_end_ms",
        "maximum_active_book_gap_ms",
        "maximum_allowed_active_book_gap_ms",
    )
    return {
        "state": "technically_censored",
        "exit_reason": None,
        "technical_incomplete_reason": "active_book_path_gap",
        "route": f"{_STRATEGY}|ETH",
        "side": lifecycle["side"],
        "entry_time_ms": lifecycle["entry_time_ms"],
        "current_exit_time_ms": lifecycle["current_exit_time_ms"],
        "deadline_time_ms": lifecycle["deadline_time_ms"],
        "stop_bps": contract["stop_bps"],
        **{field: lifecycle[field] for field in fields},
    }


def _require_identity(attempt: Record, contract: Record) -> None:
    expected = {
        "status": "active_book_path_gap",
        "strategy_id": _STRATEGY,
        "candidate_strategy_id": _CANDIDATE,
        "symbol": "ETH",
        "source_run_id": contract.get("source_run_id"),
    }
    if any(attempt.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH censored attempt identity is invalid")
    if attempt.get("side") not in {"long", "short"}:
        raise ValueError("V58 ETH censored attempt side is invalid")
    for field in ("entry_price", "position_quantity"):
        _positive_number(attempt.get(field), f"ETH {field}")
    for field in ("entry_time_ms", "current_exit_time_ms", "deadline_time_ms"):
        _positive_integer(attempt.get(field), f"ETH {field}")


def _require_gap(attempt: Record) -> None:
    start = _positive_integer(attempt.get("active_book_gap_start_ms"), "gap start")
    end = _positive_integer(attempt.get("active_book_gap_end_ms"), "gap end")
    maximum = _positive_integer(attempt.get("maximum_active_book_gap_ms"), "gap")
    allowed = _positive_integer(
        attempt.get("maximum_allowed_active_book_gap_ms"), "allowed gap"
    )
    current = _positive_integer(attempt.get("current_exit_time_ms"), "current time")
    if end - start != maximum or maximum <= allowed or end > current:
        raise ValueError("V58 ETH active book gap evidence is inconsistent")


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"V58 ETH {label} must be a positive integer")
    return value


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"V58 ETH {label} must be positive")
    return float(value)
