"""Bound recovery to an exact owned cancellation-timeout exit, preserving history."""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from hypervector.live.asset_order_restart import AssetOrderRestartError
from hypervector.live.asset_order_restart_context import pending_position_context

_TIMEOUT = re.compile(r"cancel remains ambiguous after exact oid lookup: ([1-9][0-9]*)")
_MUTATIONS = frozenset(
    {
        "order_intent",
        "cancel_intent",
        "order_acknowledgement",
        "close",
        "stop_order",
        "target_order",
    }
)


@dataclass(frozen=True)
class CancelFaultContext:
    """Exact cancel identity and the preceding owned exit context."""

    records: list[dict[str, object]]
    oid: int


def records_before_cancel_fault(records: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return a recovery-only view without changing the original failure history."""
    context = cancel_fault_context(records)
    return records if context is None else context.records


def cancel_fault_context(records: list[dict[str, object]]) -> CancelFaultContext | None:
    """Recognize only a validated cancellation timeout; retain unrelated faults."""
    boundary = _fault_boundary(records)
    if boundary is None:
        return None
    index, reason, oid = boundary
    cancel_index = _matching_cancel(records, index, reason, oid)
    context = pending_position_context(records[:cancel_index], "EXIT_PENDING")
    if oid not in {context.stop_oid, context.target_oid}:
        raise AssetOrderRestartError("cancel restart oid is not owned by the interrupted exit")
    for record in records[cancel_index + 1 :]:
        if record.get("event_type") in _MUTATIONS:
            raise AssetOrderRestartError("cancel restart has contradictory later mutation evidence")
    context_end = next(
        position
        for position in range(cancel_index + 1, index + 1)
        if records[position].get("event_type") == "state_transition"
    )
    return CancelFaultContext(records[:context_end], oid)


def _fault_boundary(records: list[dict[str, object]]) -> tuple[int, str, int] | None:
    for index in range(len(records) - 1, -1, -1):
        record = records[index]
        if record.get("event_type") != "state_transition":
            continue
        payload = _payload(record)
        if payload.get("state") in {"STOPPED", "PREFLIGHT"}:
            continue
        reason = payload.get("last_fault")
        if payload.get("state") != "FAULTED" or not isinstance(reason, str):
            return None
        match = _TIMEOUT.fullmatch(reason)
        return None if match is None else (index, reason, int(match.group(1)))
    return None


def _matching_cancel(records: list[dict[str, object]], before: int, reason: str, oid: int) -> int:
    saw_fault = False
    for index in range(before - 1, -1, -1):
        record = records[index]
        kind = record.get("event_type")
        if kind == "fault":
            if _payload(record).get("reason") != reason:
                raise AssetOrderRestartError("cancel restart fault evidence is inconsistent")
            saw_fault = True
        elif kind == "cancel_intent":
            payload = _payload(record)
            if (
                not saw_fault
                or payload.get("operation") != "cancel_order"
                or payload.get("oid") != oid
            ):
                raise AssetOrderRestartError("cancel restart lacks its exact timed-out intent")
            return index
        elif kind == "state_transition":
            payload = _payload(record)
            if payload.get("state") in {"PREFLIGHT", "STOPPED"}:
                continue
            if payload.get("state") == "FAULTED" and payload.get("last_fault") == reason:
                continue
            break
    raise AssetOrderRestartError("cancel restart lacks a matching fault and cancel intent")


def _payload(record: Mapping[str, object]) -> Mapping[str, object]:
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        raise AssetOrderRestartError("cancel restart payload must be an object")
    return payload
