"""Durable proof that a partial protective exit completed before residual-order cleanup."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime

from hypervector.live.asset_live_snapshot import AssetLiveSnapshot
from hypervector.live.asset_order_restart import AssetOrderRestartError
from hypervector.live.asset_order_restart_context import (
    PendingPositionContext,
    pending_position_context,
)
from hypervector.live.asset_protective_execution_evidence import (
    ProtectiveExecutionProgress,
    observe_protective_execution,
)
from hypervector.live.asset_protective_journal import (
    validate_protective_checkpoint_payload,
)
from hypervector.live.asset_live_journal_orders import intent_for_oid
from hypervector.live.asset_live_journal_values import (
    payload,
    required_positive_int,
)

CLEANUP_PHASE = "protective_exit_cleanup_pending"
CLEANUP_UNRESOLVED = "protective exit cleanup remains unresolved"


@dataclass(frozen=True)
class ProtectiveCleanupContext:
    """Retain proven completion separately from the remaining cancellation obligation."""

    owner: PendingPositionContext
    owner_payload: Mapping[str, object]
    close_oid: int | None
    completed: ProtectiveExecutionProgress
    marker_index: int
    completion_recorded: bool = False


def cleanup_checkpoint_payload(
    owner: AssetLiveSnapshot, completed: ProtectiveExecutionProgress
) -> dict[str, object]:
    """Persist original ownership and exact completed receipts before any cleanup mutation."""
    return {
        "phase": CLEANUP_PHASE,
        "owner": owner.as_payload(),
        "completed_progress": completed.as_payload(),
    }


def pending_protective_cleanup(records: list[dict[str, object]]) -> ProtectiveCleanupContext | None:
    """Find an unfinished cleanup marker and authenticate its original completion proof."""
    for index in range(len(records) - 1, -1, -1):
        row = records[index]
        if row.get("event_type") == "close" and (
            payload(row).get("phase") == CLEANUP_PHASE
            or "completed_progress" in payload(row)
            or "owner" in payload(row)
        ):
            try:
                context = _validate_marker(records, index)
                recorded, flat_committed = _completion_status(records, context)
                return None if flat_committed else replace(context, completion_recorded=recorded)
            except ValueError as exc:
                raise AssetOrderRestartError(f"protective cleanup checkpoint invalid: {exc}") from exc
    return None


def completed_cleanup_event(body: Mapping[str, object], context: ProtectiveCleanupContext) -> bool:
    """Recognize the exact final economic event proved by this cleanup checkpoint."""
    return body == {
        "reason": "protective_stop_remainder",
        "verified_flat": True,
        "owned_oids": sorted({fill.oid for fill in context.completed.fills}),
    }


def _completion_status(
    records: list[dict[str, object]], context: ProtectiveCleanupContext
) -> tuple[bool, bool]:
    recorded = False
    for row in records[context.marker_index + 1 :]:
        body = payload(row)
        if row.get("event_type") == "close" and body.get("verified_flat") is True:
            if not completed_cleanup_event(body, context):
                raise ValueError("cleanup completion event contradicts its exact receipts")
            recorded = True
        if (
            recorded
            and row.get("event_type") == "state_transition"
            and body.get("state") in {"FLAT", "STOPPED"}
            and body.get("position_size_signed") == 0.0
        ):
            return True, True
    return recorded, False


def _validate_marker(records: list[dict[str, object]], index: int) -> ProtectiveCleanupContext:
    body = payload(records[index])
    if (
        set(body) != {"phase", "owner", "completed_progress"}
        or body.get("phase") != CLEANUP_PHASE
        or not isinstance(body["owner"], Mapping)
    ):
        raise ValueError("cleanup marker requires exact owner and completed receipt fields")
    raw = body["owner"]
    if set(raw) != set(AssetLiveSnapshot().as_payload()) or raw.get("last_fault") is not None:
        raise ValueError("cleanup marker has malformed owner fields")
    owner = pending_position_context(
        [{"event_type": "state_transition", "payload": raw}], "EXIT_PENDING"
    )
    if (
        owner != _preceding_owner(records[:index])
        or not owner.protective_progress.stop_exit_required
        or owner.stop_oid is None
    ):
        raise ValueError("cleanup owner differs from the preceding stop-exit obligation")
    close_oid = _close_identity(records[:index], raw.get("close_oid"))
    completed = ProtectiveExecutionProgress.from_payload(body["completed_progress"])
    validate_protective_checkpoint_payload(records[:index], raw, intent_for_oid)
    validate_protective_checkpoint_payload(
        records[:index], {**raw, "protective_progress": completed.as_payload()}, intent_for_oid
    )
    stamp = datetime.fromisoformat(str(records[index].get("observed_at_utc")))
    if stamp.utcoffset() is None:
        raise ValueError("cleanup checkpoint clock must be timezone-aware")
    verified = observe_protective_execution(
        previous_size_signed=owner.position_size_signed,
        current_size_signed=0.0,
        opened_at_ms=owner.opened_at_ms,
        observed_at_ms=int(stamp.timestamp() * 1000),
        stop_oid=owner.stop_oid,
        target_oid=owner.target_oid,
        prior=owner.protective_progress,
        fills=completed.fills,
        additional_exit_oids=() if close_oid is None else (close_oid,),
    )
    if verified != completed:
        raise ValueError("cleanup checkpoint does not prove the complete original reduction")
    return ProtectiveCleanupContext(owner, raw, close_oid, completed, index)


def _preceding_owner(records: list[dict[str, object]]) -> PendingPositionContext:
    for index in range(len(records) - 1, -1, -1):
        row = records[index]
        if row.get("event_type") != "state_transition":
            continue
        state = payload(row).get("state")
        if state in {"PREFLIGHT", "FAULTED"}:
            continue
        if state not in {"EXIT_PENDING", "STOPPED"}:
            raise ValueError("cleanup lacks a preceding owned exit state")
        return pending_position_context(records[: index + 1], str(state))
    raise ValueError("cleanup lacks a durable owned position")


def _close_identity(records: list[dict[str, object]], value: object) -> int | None:
    if value is None:
        return None
    oid = required_positive_int(value, "cleanup close oid")
    accepted = any(
        row.get("event_type") == "close"
        and payload(row).get("oid") == oid
        and payload(row).get("accepted") is True
        and payload(row).get("operation")
        in {"reduce_only_close", "reduce_only_close_restart_recovery"}
        for row in records
    )
    intent = intent_for_oid(records, oid)
    if not accepted or intent is None or payload(intent).get("operation") != "reduce_only_close":
        raise ValueError("cleanup close lacks its original accepted owned intent")
    return oid
