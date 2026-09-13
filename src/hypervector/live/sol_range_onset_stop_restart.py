"""Recover an exact stop and complete its saved target contract before OPEN."""

from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.sol_order_restart import (
    PendingSolOrderIntent,
    SolOrderRestartError,
)
from hypervector.live.sol_order_restart_context import (
    PendingPositionContext,
    pending_position_context_for_intent,
    positive_number,
)
from hypervector.live.sol_order_submission import SolOrderSubmission
from hypervector.live.sol_range_onset_config import SolRangeOnsetConfig
from hypervector.live.sol_range_onset_consistency import SolReconciliationPoller
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_execution_plan import legacy_execution_plan
from hypervector.live.sol_range_onset_exit_restart import (
    RecoveredPendingEntry,
    resume_unprotected_position,
)
from hypervector.live.sol_range_onset_reconcile import SolStartupReconciliationError
from hypervector.live.sol_range_onset_state import SolLiveStateMachine
from hypervector.live.sol_range_onset_target import (
    EmergencyFlattenProtocol,
    complete_entry_protection,
)
from hypervector.live.sol_range_onset_verification import verify_protected_position
from hypervector.live.sol_startup_support import _fault_and_raise, _recover_intent_ack


def recover_pending_stop(
    *,
    config: SolRangeOnsetConfig,
    events: SolLiveEngineEvents,
    machine: SolLiveStateMachine,
    orders: SolOrderSubmission,
    pending: PendingSolOrderIntent,
    records: list[dict[str, object]],
    venue: SolReconciliationSnapshot,
    poller: SolReconciliationPoller,
    emergency_flatten: EmergencyFlattenProtocol,
) -> RecoveredPendingEntry | None:
    """Adopt the committed stop without resubmission and finish required protection."""
    try:
        context = pending_position_context_for_intent(
            records, "PROTECTING", pending.client_order_id
        )
    except SolOrderRestartError as exc:
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
        _fault_and_raise(events, SolOrderRestartError("recovered stop is unresolved"))
    _finish_stop(
        config, context, ack.oid, venue, machine, events, orders, poller, emergency_flatten
    )
    return None


def _finish_stop(
    config: SolRangeOnsetConfig,
    context: PendingPositionContext,
    stop_oid: int,
    venue: SolReconciliationSnapshot,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
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
    except SolOrderRestartError as exc:
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
    venue: SolReconciliationSnapshot,
    events: SolLiveEngineEvents,
) -> bool:
    try:
        return verify_protected_position(
            entry_oid=context.entry_oid,
            stop_oid=stop_oid,
            position_size_signed=context.position_size_signed,
            opened_at_ms=context.opened_at_ms,
            venue=venue,
        )
    except SolStartupReconciliationError as exc:
        _fault_and_raise(events, exc)
