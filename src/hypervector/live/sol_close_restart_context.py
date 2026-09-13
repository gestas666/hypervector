"""Preserve the original acknowledged close across bounded fill-visibility failures."""

from collections.abc import Mapping

from hypervector.live.sol_order_restart import interrupted_lifecycle_intent
from hypervector.live.sol_order_restart_context import (
    pending_position_context_for_intent,
)

PARTIAL_CLOSE_UNRESOLVED = "close acknowledged but protected exposure remains"
READ_ONLY_RESTART_EVENTS = frozenset(
    {
        "session_start",
        "effective_mode",
        "configuration_identity",
        "reconciliation",
        "position",
        "fill",
        "fee",
        "funding",
        "funding_reconciliation_window",
        "liquidation_price",
        "book_observation",
        "heartbeat",
        "runtime_fault",
    }
)


def records_before_partial_close_fault(
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return an exact retry view only while later records contain no new mutation/progress."""
    for index, record in enumerate(records):
        payload = record.get("payload")
        if (
            record.get("event_type") != "fault"
            or not isinstance(payload, Mapping)
            or payload.get("reason") != PARTIAL_CLOSE_UNRESOLVED
        ):
            continue
        prefix = records[:index]
        pending = interrupted_lifecycle_intent(prefix)
        if pending is None or pending.operation != "reduce_only_close":
            continue
        context = pending_position_context_for_intent(
            prefix,
            "EXIT_PENDING",
            pending.client_order_id,
        )
        ack = _original_ack(prefix, pending.client_order_id)
        if ack is None:
            continue
        expected = {
            "entry_oid": context.entry_oid,
            "stop_oid": context.stop_oid,
            "close_oid": ack["oid"],
            "position_size_signed": context.position_size_signed,
            "opened_at_ms": context.opened_at_ms,
        }
        if all(_retry_record(row, pending.client_order_id, expected) for row in records[index:]):
            return prefix
    return records


def _original_ack(records: list[dict[str, object]], client_id: str) -> Mapping[str, object] | None:
    matching = []
    for row in records:
        payload = row.get("payload")
        if (
            row.get("event_type") == "close"
            and isinstance(payload, Mapping)
            and payload.get("client_order_id") == client_id
        ):
            matching.append(payload)
    if len(matching) != 1 or not _same_ack(matching[0], client_id, matching[0].get("oid")):
        return None
    return matching[0]


def _same_ack(payload: Mapping[str, object], client_id: str, oid: object) -> bool:
    return (
        type(oid) is int
        and oid > 0
        and payload.get("operation") in {"reduce_only_close", "reduce_only_close_restart_recovery"}
        and payload.get("client_order_id") == client_id
        and payload.get("oid") == oid
        and payload.get("accepted") is True
        and payload.get("status") in {"filled", "canceled"}
    )


def _retry_record(
    record: Mapping[str, object], client_id: str, expected: Mapping[str, object]
) -> bool:
    kind, payload = record.get("event_type"), record.get("payload")
    if kind in READ_ONLY_RESTART_EVENTS:
        return True
    if not isinstance(payload, Mapping):
        return False
    if kind == "fault":
        return payload.get("reason") == PARTIAL_CLOSE_UNRESOLVED
    if kind == "close":
        return _same_ack(payload, client_id, expected["close_oid"])
    if kind != "state_transition":
        return False
    state = payload.get("state")
    if state == "PREFLIGHT":
        return payload.get("position_size_signed", 0) == 0
    if state not in {"FAULTED", "EXIT_PENDING"}:
        return False
    if state == "FAULTED" and payload.get("last_fault") != PARTIAL_CLOSE_UNRESOLVED:
        return False
    return all(
        payload.get(key) == value
        for key, value in expected.items()
        if state == "FAULTED" or key != "close_oid"
    )
