"""Age-aware execution-process lifecycle projection for live checkpoints."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import TypeAlias

Record: TypeAlias = Mapping[str, object]
_FAULT_STATES = frozenset({"FAULT", "FAULTED"})
_TERMINAL_STATES = frozenset({"STOPPED", *_FAULT_STATES})


def build_live_lifecycle(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    *,
    run_id: str,
    observed_at: datetime,
    heartbeat_stale_after_seconds: float | None,
) -> dict[str, object]:
    """Project process health without treating sidecar writes as heartbeats."""
    cohort = _run_rows(cohort_records, run_id)
    heartbeat = _latest_event(cohort, "heartbeat")
    runtime_fault = _latest_event(cohort, "runtime_fault")
    status = _payload_text(heartbeat, "status") if heartbeat else None
    fault_type = (
        _payload_text(runtime_fault, "exception_type") if runtime_fault else None
    )
    heartbeat_at = _event_time(heartbeat)
    age = _heartbeat_age(observed_at, heartbeat_at)
    states = {
        symbol: _asset_state(_run_rows(records, run_id))
        for symbol, records in sorted(asset_records.items())
    }
    values = tuple(states.values())
    stale = _is_stale(age, heartbeat_stale_after_seconds)
    faulted = [symbol for symbol, state in states.items() if state in _FAULT_STATES]
    state = _classify_lifecycle(
        status,
        values,
        stale=stale,
        runtime_fault=runtime_fault is not None,
    )
    return {
        "state": state,
        "backend_process_health": _process_health(state, status),
        "cohort_heartbeat_status": status,
        "cohort_heartbeat_observed_at_utc": (
            heartbeat_at.isoformat() if heartbeat_at is not None else None
        ),
        "cohort_heartbeat_age_seconds": age,
        "runtime_fault_exception_type": fault_type,
        "cohort_last_event_type": cohort[-1].get("event_type") if cohort else None,
        "cohort_last_observed_at_utc": (
            cohort[-1].get("observed_at_utc") if cohort else None
        ),
        "asset_states": states,
        "faulted_assets": faulted,
        "all_assets_terminal": bool(values)
        and all(value in _TERMINAL_STATES for value in values),
    }


def _classify_lifecycle(
    heartbeat_status: str | None,
    states: Sequence[str | None],
    *,
    stale: bool,
    runtime_fault: bool,
) -> str:
    if runtime_fault:
        return "backend_runtime_fault"
    if not states or any(state is None for state in states):
        return "lifecycle_evidence_incomplete"
    if any(state in _FAULT_STATES for state in states):
        return "asset_faulted"
    stopped = sum(state == "STOPPED" for state in states)
    if stopped == len(states):
        return (
            "stale_running_heartbeat_after_asset_stop"
            if heartbeat_status == "running"
            else "stopped_consistent"
        )
    if stopped:
        return "mixed_asset_lifecycle"
    if stale:
        return "backend_heartbeat_stale"
    if heartbeat_status == "running":
        return "running_consistent"
    if heartbeat_status == "degraded":
        return "running_degraded"
    return "cohort_not_running_while_assets_active"


def _process_health(state: str, heartbeat_status: str | None) -> str:
    if state == "backend_runtime_fault":
        return "faulted"
    if state == "backend_heartbeat_stale":
        return "stale"
    if state in {"running_consistent", "stale_running_heartbeat_after_asset_stop"}:
        return "healthy"
    if heartbeat_status == "degraded":
        return "degraded"
    return "unknown"


def _heartbeat_age(
    observed_at: datetime, heartbeat_at: datetime | None
) -> float | None:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("checkpoint generation time must be timezone-aware")
    if heartbeat_at is None:
        return None
    return max(0.0, (observed_at - heartbeat_at).total_seconds())


def _is_stale(age: float | None, threshold: float | None) -> bool:
    if threshold is None:
        return False
    if threshold <= 0.0:
        raise ValueError("heartbeat stale threshold must be positive")
    return age is None or age > threshold


def _event_time(record: Record | None) -> datetime | None:
    if record is None:
        return None
    value = record.get("observed_at_utc")
    if not isinstance(value, str):
        raise ValueError("heartbeat observed_at_utc must be text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("heartbeat observed_at_utc must be timezone-aware")
    return parsed


def _run_rows(records: Sequence[Record], run_id: str) -> tuple[Record, ...]:
    return tuple(row for row in records if row.get("run_id") == run_id)


def _latest_event(records: Sequence[Record], event_type: str) -> Record | None:
    return next(
        (row for row in reversed(records) if row.get("event_type") == event_type),
        None,
    )


def _asset_state(records: Sequence[Record]) -> str | None:
    transition = _latest_event(records, "state_transition")
    return _payload_text(transition, "state") if transition else None


def _payload_text(record: Record, key: str) -> str | None:
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("ledger payload must be an object")
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value.strip()
