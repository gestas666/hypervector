"""Recover unresolved durable SOL order intent from the live ledger."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from hypervector.live.sol_order_identity import validate_client_order_id

SolOrderOperation = Literal[
    "entry", "protective_stop", "raise_protective_stop", "target", "reduce_only_close"
]
_OPERATIONS = frozenset(
    {"entry", "protective_stop", "raise_protective_stop", "target", "reduce_only_close"}
)
_ACK_EVENTS = frozenset(
    {"order_acknowledgement", "stop_order", "target_order", "close"}
)
_STATE_OPERATIONS: dict[str, SolOrderOperation] = {
    "ENTRY_PENDING": "entry",
    "PROTECTING": "protective_stop",
    "TARGET_PENDING": "target",
    "EXIT_PENDING": "reduce_only_close",
}
_TARGET_VISIBILITY_FAULT = (
    "target acknowledged but complete bracket is not venue-visible"
)


class SolOrderRestartError(RuntimeError):
    """Ledger intent cannot be reduced to one exact pending mutation."""


@dataclass(frozen=True)
class PendingSolOrderIntent:
    """One mutation persisted before submission but not yet acknowledged."""

    operation: SolOrderOperation
    client_order_id: str
    observed_at_utc: str
    payload: Mapping[str, object]


def pending_order_intent(
    records: Sequence[Mapping[str, object]],
) -> PendingSolOrderIntent | None:
    """Return the sole unresolved CLOID intent or fail on ambiguous history."""
    pending, _ = _pending_intent_state(records)
    if len(pending) > 1:
        raise SolOrderRestartError("multiple unresolved order intents remain")
    return next(iter(pending.values()), None)


def _pending_intent_state(
    records: Sequence[Mapping[str, object]],
) -> tuple[dict[str, PendingSolOrderIntent], set[str]]:
    pending: dict[str, PendingSolOrderIntent] = {}
    unsent: set[str] = set()
    for record in records:
        event_type = record.get("event_type")
        payload = _mapping(record.get("payload"), "order event payload")
        if event_type == "order_intent":
            intent = _parse_intent(record, payload)
            if intent.client_order_id in pending:
                raise SolOrderRestartError("duplicate unresolved client order id")
            if intent.client_order_id in unsent:
                raise SolOrderRestartError("a non-submitted entry identity was reused")
            pending[intent.client_order_id] = intent
            continue
        if event_type == "entry_not_submitted":
            client_id = _resolve_non_submitted(payload, pending)
            pending.pop(client_id)
            unsent.add(client_id)
            continue
        if event_type in _ACK_EVENTS:
            raw_client_id = payload.get("client_order_id")
            if isinstance(raw_client_id, str):
                if raw_client_id in unsent:
                    raise SolOrderRestartError(
                        "non-submitted entry has a contradictory acknowledgement"
                    )
                pending.pop(raw_client_id, None)
    return pending, unsent


def _resolve_non_submitted(
    payload: Mapping[str, object],
    pending: Mapping[str, PendingSolOrderIntent],
) -> str:
    fields = {
        "operation",
        "client_order_id",
        "submitted",
        "reason",
        "decision_time_ms",
        "submission_observed_at_ms",
        "submission_age_ms",
        "submission_limit_ms",
        "submission_boundary",
    }
    if (
        set(payload) != fields
        or payload["operation"] != "entry"
        or payload["submitted"] is not False
    ):
        raise SolOrderRestartError("malformed non-submitted entry outcome")
    client_id = payload["client_order_id"]
    if not isinstance(client_id, str) or client_id not in pending:
        raise SolOrderRestartError("non-submitted entry lacks matching pending intent")
    intent = pending[client_id]
    if intent.operation != "entry" or payload["reason"] != "stale_before_submission":
        raise SolOrderRestartError(
            "non-submission cannot resolve this operation or reason"
        )
    boundary = payload["submission_boundary"]
    if not isinstance(boundary, str) or boundary not in {
        "adapter_dispatch",
        "sdk_dispatch",
    }:
        raise SolOrderRestartError("non-submission has an unsupported boundary")
    contract = _mapping(intent.payload.get("entry_deadline"), "entry deadline contract")
    _validate_expiry_timing(payload, contract)
    return client_id


def _validate_expiry_timing(
    payload: Mapping[str, object], contract: Mapping[str, object]
) -> None:
    decision, observed, age, limit = (
        _integer_milliseconds(payload[name])
        for name in (
            "decision_time_ms",
            "submission_observed_at_ms",
            "submission_age_ms",
            "submission_limit_ms",
        )
    )
    if decision < 0 or limit <= 0 or observed - decision != age or age <= limit:
        raise SolOrderRestartError("non-submission timing does not establish expiry")
    if (
        type(contract.get("decision_time_ms")) is not int
        or type(contract.get("limit_ms")) is not int
        or contract["decision_time_ms"] != decision
        or contract["limit_ms"] != limit
    ):
        raise SolOrderRestartError("non-submission differs from the persisted deadline")


def _integer_milliseconds(value: object) -> int:
    if type(value) is int:
        return value
    raise SolOrderRestartError("non-submission timing must use integer milliseconds")


def interrupted_lifecycle_intent(
    records: Sequence[Mapping[str, object]],
) -> PendingSolOrderIntent | None:
    """Return the intent after the latest still-pending lifecycle transition."""
    _, unsent = _pending_intent_state(records)
    state_index, operation = _latest_pending_state(records)
    if state_index is None or operation is None:
        return None
    matching: list[PendingSolOrderIntent] = []
    for record in records[state_index + 1 :]:
        if record.get("event_type") != "order_intent":
            continue
        payload = _mapping(record.get("payload"), "order intent payload")
        intent = _parse_intent(record, payload)
        if intent.operation == operation and intent.client_order_id not in unsent:
            matching.append(intent)
    if len(matching) > 1:
        raise SolOrderRestartError("multiple intents exist for pending lifecycle")
    return matching[0] if matching else None


def _latest_pending_state(
    records: Sequence[Mapping[str, object]],
) -> tuple[int | None, SolOrderOperation | None]:
    for index in range(len(records) - 1, -1, -1):
        record = records[index]
        if record.get("event_type") != "state_transition":
            continue
        payload = _mapping(record.get("payload"), "state transition payload")
        state = payload.get("state")
        operation = _STATE_OPERATIONS.get(state) if isinstance(state, str) else None
        if state == "FAULTED":
            return _recoverable_target_fault_state(records, index)
        return index, operation
    return None, None


def _recoverable_target_fault_state(
    records: Sequence[Mapping[str, object]],
    fault_state_index: int,
) -> tuple[int | None, SolOrderOperation | None]:
    pending_index = _previous_target_pending_index(records, fault_state_index)
    if pending_index is None:
        return None, None
    segment = records[pending_index + 1 : fault_state_index]
    faults = [
        _mapping(record.get("payload"), "fault payload")
        for record in segment
        if record.get("event_type") == "fault"
    ]
    intents = [
        _parse_intent(record, _mapping(record.get("payload"), "order intent payload"))
        for record in segment
        if record.get("event_type") == "order_intent"
    ]
    acknowledgements = [
        _mapping(record.get("payload"), "target acknowledgement payload")
        for record in segment
        if record.get("event_type") == "target_order"
    ]
    if len(faults) != 1 or faults[0].get("reason") != _TARGET_VISIBILITY_FAULT:
        return None, None
    if len(intents) != 1 or intents[0].operation != "target":
        return None, None
    if len(acknowledgements) != 1:
        return None, None
    ack = acknowledgements[0]
    if ack.get("accepted") is not True or ack.get("oid") is None:
        return None, None
    if ack.get("client_order_id") != intents[0].client_order_id:
        return None, None
    return pending_index, "target"


def _previous_target_pending_index(
    records: Sequence[Mapping[str, object]],
    before_index: int,
) -> int | None:
    for index in range(before_index - 1, -1, -1):
        record = records[index]
        if record.get("event_type") != "state_transition":
            continue
        payload = _mapping(record.get("payload"), "state transition payload")
        return index if payload.get("state") == "TARGET_PENDING" else None
    return None


def _parse_intent(
    record: Mapping[str, object],
    payload: Mapping[str, object],
) -> PendingSolOrderIntent:
    operation = payload.get("operation")
    if operation not in _OPERATIONS:
        raise SolOrderRestartError(f"unsupported pending operation: {operation!r}")
    observed = record.get("observed_at_utc")
    if not isinstance(observed, str) or not observed.strip():
        raise SolOrderRestartError("pending order intent lacks observed_at_utc")
    client_order_id = payload.get("client_order_id")
    if not isinstance(client_order_id, str):
        raise SolOrderRestartError("pending order intent lacks client_order_id")
    return PendingSolOrderIntent(
        operation=operation,
        client_order_id=validate_client_order_id(client_order_id),
        observed_at_utc=observed,
        payload=dict(payload),
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise SolOrderRestartError(f"{label} must be an object")
    return value
