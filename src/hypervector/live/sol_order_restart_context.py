"""Strict position context parsing for interrupted SOL order lifecycles."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from hypervector.live.cohort_execution_plan import (
    BoundExecutionPlan,
    CohortExecutionPlanError,
)
from hypervector.live.sol_order_identity import validate_client_order_id
from hypervector.live.sol_order_restart import (
    PendingSolOrderIntent,
    SolOrderRestartError,
)


@dataclass(frozen=True)
class PendingPositionContext:
    """Owned position identity persisted before stop or close interruption."""

    entry_oid: int
    stop_oid: int | None
    position_size_signed: float
    opened_at_ms: int
    execution_plan: BoundExecutionPlan | None = None
    target_oid: int | None = None
    target_price: float | None = None


def pending_position_context(
    records: list[dict[str, object]],
    expected_state: str,
) -> PendingPositionContext:
    """Parse exact owned position context from the latest state transition."""
    for record in reversed(records):
        if record.get("event_type") != "state_transition":
            continue
        payload = record.get("payload")
        if not isinstance(payload, Mapping):
            raise SolOrderRestartError("state transition payload must be an object")
        if payload.get("state") != expected_state:
            raise SolOrderRestartError(
                f"pending order requires local state {expected_state}"
            )
        return _position_context(payload)
    raise SolOrderRestartError("pending order lacks a state transition")


def pending_position_context_for_intent(
    records: list[dict[str, object]],
    expected_state: str,
    client_order_id: str,
) -> PendingPositionContext:
    """Parse the exact lifecycle state immediately preceding one intent."""
    return _position_context(
        _state_for_intent(records, expected_state, client_order_id)
    )


def execution_plan_for_intent(
    records: list[dict[str, object]],
    expected_state: str,
    client_order_id: str,
) -> BoundExecutionPlan | None:
    """Restore the plan bound to an exact intent, including after a later fault."""
    payload = _state_for_intent(records, expected_state, client_order_id)
    return _execution_plan(payload.get("execution_plan"))


def pending_entry_opened_at_ms(
    pending: PendingSolOrderIntent, venue_timestamp_ms: int
) -> int:
    """Preserve the durable decision; legacy intents retain their venue-time fallback."""
    if pending.operation != "entry":
        raise SolOrderRestartError("entry clock requires an entry intent")
    venue_time = _nonnegative_integer(venue_timestamp_ms, "entry venue timestamp")
    if "entry_deadline" not in pending.payload:
        return venue_time
    deadline = pending.payload["entry_deadline"]
    if not isinstance(deadline, Mapping):
        raise SolOrderRestartError("pending entry deadline must be an object")
    decision = _nonnegative_integer(
        deadline.get("decision_time_ms"), "entry decision time"
    )
    _positive_integer(deadline.get("limit_ms"), "entry deadline limit")
    if decision > venue_time:
        raise SolOrderRestartError(
            "entry decision time exceeds recovered venue timestamp"
        )
    return decision


def _state_for_intent(
    records: list[dict[str, object]], expected_state: str, client_order_id: str
) -> Mapping[str, object]:
    identity = validate_client_order_id(client_order_id)
    intent_indexes: list[int] = []
    for index, record in enumerate(records):
        if record.get("event_type") != "order_intent":
            continue
        payload = record.get("payload")
        if not isinstance(payload, Mapping):
            raise SolOrderRestartError("order intent payload must be an object")
        if payload.get("client_order_id") == identity:
            intent_indexes.append(index)
    if len(intent_indexes) != 1:
        raise SolOrderRestartError("pending intent identity is not unique")
    for record in reversed(records[: intent_indexes[0]]):
        if record.get("event_type") != "state_transition":
            continue
        payload = record.get("payload")
        if not isinstance(payload, Mapping):
            raise SolOrderRestartError("state transition payload must be an object")
        if payload.get("state") != expected_state:
            raise SolOrderRestartError(
                f"pending order requires local state {expected_state}"
            )
        return payload
    raise SolOrderRestartError("pending intent lacks a preceding state transition")


def _position_context(payload: Mapping[str, object]) -> PendingPositionContext:
    return PendingPositionContext(
        entry_oid=_positive_integer(payload.get("entry_oid"), "entry_oid"),
        stop_oid=_optional_positive_integer(payload.get("stop_oid"), "stop_oid"),
        position_size_signed=_nonzero_number(
            payload.get("position_size_signed"), "position size"
        ),
        opened_at_ms=_nonnegative_integer(payload.get("opened_at_ms"), "opened_at_ms"),
        execution_plan=_execution_plan(payload.get("execution_plan")),
        target_oid=_optional_positive_integer(payload.get("target_oid"), "target_oid"),
        target_price=_optional_positive_number(
            payload.get("target_price"), "target_price"
        ),
    )


def latest_lifecycle_state(records: list[dict[str, object]]) -> str | None:
    """Return the most recently persisted lifecycle state, if any."""
    for record in reversed(records):
        if record.get("event_type") != "state_transition":
            continue
        payload = record.get("payload")
        if not isinstance(payload, Mapping):
            raise SolOrderRestartError("state transition payload must be an object")
        state = payload.get("state")
        if not isinstance(state, str) or not state:
            raise SolOrderRestartError("state transition state must be text")
        return state
    return None


def owned_open_record(
    context: PendingPositionContext,
    stop_oid: int,
    profile_fingerprint: str | None = None,
) -> dict[str, object]:
    """Build one synthetic OPEN record for the shared ownership verifier."""
    record: dict[str, object] = {
        "event_type": "state_transition",
        "payload": {
            "state": "OPEN",
            "entry_oid": context.entry_oid,
            "stop_oid": stop_oid,
            "position_size_signed": context.position_size_signed,
            "opened_at_ms": context.opened_at_ms,
            "execution_plan": (
                context.execution_plan.as_payload()
                if context.execution_plan is not None
                else None
            ),
            "target_oid": context.target_oid,
            "target_price": context.target_price,
        },
    }
    if profile_fingerprint is not None:
        record["profile_fingerprint"] = profile_fingerprint
    return record


def execution_plan_for_state(
    records: list[dict[str, object]],
    expected_state: str,
) -> BoundExecutionPlan | None:
    """Restore the plan serialized with one exact lifecycle state."""
    for record in reversed(records):
        if record.get("event_type") != "state_transition":
            continue
        payload = record.get("payload")
        if not isinstance(payload, Mapping) or payload.get("state") != expected_state:
            raise SolOrderRestartError(
                f"pending order requires local state {expected_state}"
            )
        return _execution_plan(payload.get("execution_plan"))
    raise SolOrderRestartError("pending order lacks a state transition")


def required_text(value: object, label: str) -> str:
    """Return non-empty text or reject corrupt restart context."""
    if not isinstance(value, str) or not value.strip():
        raise SolOrderRestartError(f"{label} must be non-empty text")
    return value.strip()


def positive_number(value: object, label: str) -> float:
    """Return a finite positive number or reject corrupt restart context."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SolOrderRestartError(f"{label} must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise SolOrderRestartError(f"{label} must be positive and finite")
    return parsed


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SolOrderRestartError(f"{label} must be a positive integer")
    return value


def _optional_positive_integer(value: object, label: str) -> int | None:
    return None if value is None else _positive_integer(value, label)


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SolOrderRestartError(f"{label} must be a nonnegative integer")
    return value


def _nonzero_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SolOrderRestartError(f"{label} must be numeric")
    parsed = positive_number(abs(value), label)
    return -parsed if value < 0 else parsed


def _optional_positive_number(value: object, label: str) -> float | None:
    return None if value is None else positive_number(value, label)


def _execution_plan(value: object) -> BoundExecutionPlan | None:
    if value is None:
        return None
    try:
        return BoundExecutionPlan.from_payload(value)
    except CohortExecutionPlanError as exc:
        raise SolOrderRestartError(f"invalid persisted execution plan: {exc}") from exc
