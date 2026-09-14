"""Restrict post-completion recovery to exact owned cancellation attempts and read-only retries."""

from collections.abc import Mapping

from hypervector.live.sol_close_restart_context import READ_ONLY_RESTART_EVENTS
from hypervector.live.sol_order_restart import SolOrderRestartError
from hypervector.live.sol_protective_checkpoint import protective_progress_from_state
from hypervector.live.sol_protective_cleanup_checkpoint import (
    CLEANUP_UNRESOLVED,
    ProtectiveCleanupContext,
    completed_cleanup_event,
)
from hypervector.live.sol_range_onset_live_journal_values import payload


def validate_cleanup_suffix(
    records: list[dict[str, object]], context: ProtectiveCleanupContext
) -> None:
    """Reject new orders, changed ownership and unrelated faults after proven completion."""
    pending_cancel: int | None = None
    owned = {oid for oid in (context.owner.stop_oid, context.owner.target_oid) if oid is not None}
    for row in records[context.marker_index + 1 :]:
        kind, body = row.get("event_type"), payload(row)
        if kind in READ_ONLY_RESTART_EVENTS and not (kind == "fill" and _owned_fill(body, context)):
            continue
        if (
            kind == "close"
            and context.completion_recorded
            and completed_cleanup_event(body, context)
        ):
            continue
        if kind == "fault" and _cleanup_fault(body.get("reason")):
            continue
        if kind == "state_transition" and _same_state(body, context):
            continue
        if kind == "cancel_intent" and body.get("operation") == "cancel_order":
            if type(body.get("oid")) is int and body["oid"] in owned:
                pending_cancel = body["oid"]
                continue
        if kind == "order_acknowledgement" and _valid_ack(body, owned):
            if body.get("operation") == "protective_cleanup_status":
                continue
            if (
                body.get("operation") == "cancel_residual_after_close"
                and body.get("oid") == pending_cancel
            ):
                pending_cancel = None
                continue
        raise SolOrderRestartError("protective cleanup contains contradictory later evidence")


def _owned_fill(body: Mapping[str, object], context: ProtectiveCleanupContext) -> bool:
    oids = {
        context.owner.entry_oid,
        context.owner.stop_oid,
        context.owner.target_oid,
        context.close_oid,
    } - {None}
    return body.get("oid") in oids or body.get("trade_id") in {
        fill.trade_id for fill in context.completed.fills
    }


def _valid_ack(body: Mapping[str, object], owned: set[int]) -> bool:
    status = body.get("status")
    return (
        type(body.get("oid")) is int
        and body["oid"] in owned
        and type(body.get("accepted")) is bool
        and isinstance(status, str)
        and bool(status)
    )


def _cleanup_fault(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return value in {
        CLEANUP_UNRESOLVED,
        f"continuous reconciliation failed: {CLEANUP_UNRESOLVED}",
    } or (
        value.startswith("residual order cancel rejected: ")
        or value.startswith("cancel remains ambiguous after exact oid lookup: ")
    )


def _same_state(body: Mapping[str, object], context: ProtectiveCleanupContext) -> bool:
    state = body.get("state")
    if state not in {"PREFLIGHT", "FAULTED", "STOPPED", "EXIT_PENDING"}:
        return False
    if state == "FAULTED" and not _cleanup_fault(body.get("last_fault")):
        return False
    keys = {
        "entry_oid",
        "stop_oid",
        "target_oid",
        "target_price",
        "close_oid",
        "position_size_signed",
        "opened_at_ms",
        "execution_plan",
    }
    blank = {key: 0 if key == "position_size_signed" else None for key in keys}
    if all(body.get(key) == value for key, value in blank.items()):
        return state in {"PREFLIGHT", "FAULTED"} and not protective_progress_from_state(body).fills
    return (
        state != "PREFLIGHT"
        and all(body.get(key) == context.owner_payload.get(key) for key in keys)
        and protective_progress_from_state(body) == context.owner.protective_progress
    )
