"""Recover an exact stop and complete its saved target contract before OPEN."""

from hypervector.live.hyperliquid_protocol import HyperliquidReconciliationSnapshot
from hypervector.live.asset_order_restart import (
    PendingAssetOrderIntent,
    AssetOrderRestartError,
)
from hypervector.live.asset_order_restart_context import (
    PendingPositionContext,
    pending_position_context_for_intent,
    positive_number,
)
from hypervector.live.asset_order_submission import AssetOrderSubmission
from hypervector.live.asset_engine_config import AssetEngineConfig
from hypervector.live.asset_consistency import AssetReconciliationPoller
from hypervector.live.asset_engine_events import AssetLiveEngineEvents
from hypervector.live.asset_execution_plan import legacy_execution_plan
from hypervector.live.asset_exit_restart import (
    RecoveredPendingEntry,
    resume_unprotected_position,
)
from hypervector.live.asset_reconcile import AssetStartupReconciliationError
from hypervector.live.asset_state import AssetLiveStateMachine
from hypervector.live.asset_target import (
    EmergencyFlattenProtocol,
    complete_entry_protection,
)
from hypervector.live.asset_verification import verify_protected_position
from hypervector.live.asset_startup_support import _fault_and_raise, _recover_intent_ack


def recover_pending_stop(
    *,
    config: AssetEngineConfig,
    events: AssetLiveEngineEvents,
    machine: AssetLiveStateMachine,
    orders: AssetOrderSubmission,
    pending: PendingAssetOrderIntent,
    records: list[dict[str, object]],
    venue: HyperliquidReconciliationSnapshot,
    poller: AssetReconciliationPoller,
    emergency_flatten: EmergencyFlattenProtocol,
) -> RecoveredPendingEntry | None:
    """Adopt the committed stop without resubmission and finish required protection."""
    try:
        context = pending_position_context_for_intent(
            records, "PROTECTING", pending.client_order_id
        )
    except AssetOrderRestartError as exc:
        _fault_and_raise(events, exc)
    ack = _recover_intent_ack(events, orders, pending)
    events.emit_ack("protective_stop_restart_recovery", ack, event_type="stop_order")
    reduced = ack.status == "filled" and venue.position.size_signed != 0.0
    if ack.status in {"canceled", "rejected"} or reduced:
        return resume_unprotected_position(
            events=events,
            machine=machine,
            records=records,
            expected_state="PROTECTING",
            venue=venue,
            allow_reduced_size=reduced,
            context=context,
        )
    if not ack.accepted or ack.oid is None:
        _fault_and_raise(events, AssetOrderRestartError("recovered stop is unresolved"))
    _finish_stop(
        config, context, ack.oid, venue, machine, events, orders, poller, emergency_flatten
    )
    return None


def _finish_stop(
    config: AssetEngineConfig,
    context: PendingPositionContext,
    stop_oid: int,
    venue: HyperliquidReconciliationSnapshot,
    machine: AssetLiveStateMachine,
    events: AssetLiveEngineEvents,
    orders: AssetOrderSubmission,
    poller: AssetReconciliationPoller,
    emergency_flatten: EmergencyFlattenProtocol,
) -> None:
    machine.restore_protecting_position(
        entry_oid=context.entry_oid,
        position_size_signed=context.position_size_signed,
        opened_at_ms=context.opened_at_ms,
        execution_plan=context.execution_plan,
    )
    events.emit_state()
    if _stop_has_filled(context, stop_oid, venue, events):
        events.emit_reconciliation(venue)
        events.confirm_stop_fill_during_protection(stop_oid=stop_oid)
        return
    try:
        mark_price = positive_number(venue.position.entry_price, "recovered stop entry price")
    except AssetOrderRestartError as exc:
        _fault_and_raise(events, exc)
    complete_entry_protection(
        plan=context.execution_plan or legacy_execution_plan(config),
        entry_price=mark_price,
        position_size_signed=context.position_size_signed,
        stop_oid=stop_oid,
        mark_price=mark_price,
        machine=machine,
        events=events,
        orders=orders,
        poller=poller,
        emergency_flatten=emergency_flatten,
    )


def _stop_has_filled(
    context: PendingPositionContext,
    stop_oid: int,
    venue: HyperliquidReconciliationSnapshot,
    events: AssetLiveEngineEvents,
) -> bool:
    try:
        return verify_protected_position(
            entry_oid=context.entry_oid,
            stop_oid=stop_oid,
            position_size_signed=context.position_size_signed,
            opened_at_ms=context.opened_at_ms,
            venue=venue,
        )
    except AssetStartupReconciliationError as exc:
        _fault_and_raise(events, exc)
