"""Retain exact owned context through read-only partial-protection observation failures."""

from collections.abc import Mapping

from hypervector.live.asset_close_restart_context import READ_ONLY_RESTART_EVENTS
from hypervector.live.asset_order_restart import (
    AssetOrderRestartError,
    pending_order_intent,
)
from hypervector.live.asset_order_restart_context import (
    pending_position_context_for_intent,
)
from hypervector.live.asset_protective_checkpoint import (
    PARTIAL_PROTECTIVE_UNRESOLVED,
    protective_progress_from_state,
)

_FIRST_FAULTS = {
    PARTIAL_PROTECTIVE_UNRESOLVED,
    f"continuous reconciliation failed: {PARTIAL_PROTECTIVE_UNRESOLVED}",
}
_RETRY_FAULTS = _FIRST_FAULTS | {"ambiguous local state FAULTED"}
_OWNERSHIP_FIELDS = (
    "entry_oid",
    "stop_oid",
    "target_oid",
    "target_price",
    "position_size_signed",
    "opened_at_ms",
    "execution_plan",
)


def records_before_partial_protective_fault(
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return the original retry view only while every later event is read-only and consistent."""
    start = _last_owned_index(records)
    if start is None:
        return records
    fault = next(
        (
            index
            for index in range(start + 1, len(records))
            if records[index].get("event_type") == "fault"
            and _payload(records[index]).get("reason") in _FIRST_FAULTS
        ),
        None,
    )
    if fault is None:
        return records
    original = _payload(records[start])
    close_identity = _original_close_identity(records, start, fault)
    for index in range(start + 1, len(records)):
        row = records[index]
        kind = row.get("event_type")
        if kind in READ_ONLY_RESTART_EVENTS:
            continue
        body = _payload(row)
        if kind == "fault" and body.get("reason") in _RETRY_FAULTS:
            continue
        if kind == "state_transition" and _same_state(body, original, close_identity):
            continue
        if kind == "close" and _same_close(
            body, original, close_identity, before_fault=index < fault
        ):
            continue
        if kind == "order_intent" and index < fault and close_identity is not None:
            if (
                body.get("client_order_id") == close_identity[0]
                and body.get("operation") == "reduce_only_close"
            ):
                continue
        raise AssetOrderRestartError(
            "partial protective restart contains contradictory later evidence"
        )
    return records[:fault]


def _last_owned_index(records: list[dict[str, object]]) -> int | None:
    for index in range(len(records) - 1, -1, -1):
        row = records[index]
        if row.get("event_type") != "state_transition":
            continue
        body = _payload(row)
        state = body.get("state")
        if state in {"PREFLIGHT", "FAULTED"}:
            continue
        return index if state in {"OPEN", "STOPPED", "EXIT_PENDING"} else None
    return None


def _original_close_identity(
    records: list[dict[str, object]], start: int, fault: int
) -> tuple[str, int] | None:
    segment = records[start + 1 : fault]
    intents = [row for row in segment if row.get("event_type") == "order_intent"]
    if not intents:
        return None
    if len(intents) != 1 or _payload(records[start]).get("state") != "EXIT_PENDING":
        raise AssetOrderRestartError("partial protective fault has ambiguous preceding mutation")
    intent = pending_order_intent(intents)
    if intent is None or intent.operation != "reduce_only_close":
        raise AssetOrderRestartError("partial protective fault lacks its exact pending close")
    context = pending_position_context_for_intent(
        records[:fault], "EXIT_PENDING", intent.client_order_id
    )
    if not context.protective_progress.stop_exit_required:
        raise AssetOrderRestartError("partial protective fault lacks a stop-exit obligation")
    acks = [
        _payload(row)
        for row in segment
        if row.get("event_type") == "close"
        and _payload(row).get("client_order_id") == intent.client_order_id
    ]
    if len(acks) != 1 or not _accepted_close(acks[0]):
        raise AssetOrderRestartError("partial protective fault lacks a unique accepted close")
    return intent.client_order_id, acks[0]["oid"]


def _same_state(
    body: Mapping[str, object],
    original: Mapping[str, object],
    close: tuple[str, int] | None,
) -> bool:
    state = body.get("state")
    if state not in {"PREFLIGHT", "FAULTED"}:
        return False
    if state == "FAULTED" and body.get("last_fault") not in _RETRY_FAULTS:
        return False
    empty = {key: 0 if key == "position_size_signed" else None for key in _OWNERSHIP_FIELDS}
    if all(body.get(key) == value for key, value in empty.items()):
        return body.get("close_oid") is None and not protective_progress_from_state(body).fills
    return (
        state == "FAULTED"
        and all(body.get(key) == original.get(key) for key in _OWNERSHIP_FIELDS)
        and body.get("close_oid") == (close[1] if close is not None else original.get("close_oid"))
        and protective_progress_from_state(body) == protective_progress_from_state(original)
    )


def _same_close(
    body: Mapping[str, object],
    original: Mapping[str, object],
    close: tuple[str, int] | None,
    *,
    before_fault: bool,
) -> bool:
    if before_fault and body.get("intent") is True:
        return (
            protective_progress_from_state(original).stop_exit_required
            and body.get("reason") == "protective_stop_remainder"
            and body.get("stop_oid") == original.get("stop_oid")
        )
    return (
        close is not None
        and _accepted_close(body)
        and body.get("client_order_id") == close[0]
        and body.get("oid") == close[1]
    )


def _accepted_close(body: Mapping[str, object]) -> bool:
    return (
        body.get("operation") in {"reduce_only_close", "reduce_only_close_restart_recovery"}
        and body.get("accepted") is True
        and body.get("status") in {"filled", "canceled"}
        and type(body.get("oid")) is int
        and body["oid"] > 0
    )


def _payload(record: Mapping[str, object]) -> Mapping[str, object]:
    value = record.get("payload")
    if not isinstance(value, Mapping):
        raise AssetOrderRestartError("partial protective restart payload must be an object")
    return value
