"""Restart recovery for one durably committed optional target mutation."""

from __future__ import annotations

from typing import NoReturn

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolLiveAdapterProtocol,
    SolReconciliationSnapshot,
)
from hypervector.live.sol_order_restart import (
    PendingSolOrderIntent,
    SolOrderRestartError,
)
from hypervector.live.sol_order_restart_context import (
    PendingPositionContext,
    pending_position_context_for_intent,
)
from hypervector.live.sol_order_submission import (
    SolOrderRecoveryError,
    SolOrderSubmission,
    SolOrderSubmissionError,
)
from hypervector.live.sol_range_onset_bracket import (
    complete_bracket_visible,
    owned_exit_reason,
)
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_state import SolLiveStateMachine


def recover_pending_target(
    *,
    adapter: SolLiveAdapterProtocol,
    events: SolLiveEngineEvents,
    machine: SolLiveStateMachine,
    orders: SolOrderSubmission,
    pending: PendingSolOrderIntent,
    records: list[dict[str, object]],
    venue: SolReconciliationSnapshot,
) -> None:
    """Adopt the exact target CLOID or fail with the original stop preserved."""
    context = _restore_pending_target(records, pending, machine, events)
    ack = _recover_ack(events, orders, pending)
    events.emit_ack("target_restart_recovery", ack, event_type="target_order")
    if not ack.accepted or ack.oid is None:
        _fault(events, SolOrderRestartError("recovered target is unresolved"))
    if venue.position.size_signed == 0.0:
        _complete_flat_target(
            adapter=adapter,
            events=events,
            machine=machine,
            orders=orders,
            venue=venue,
            stop_oid=context.stop_oid,
            target_oid=ack.oid,
            position_size_signed=context.position_size_signed,
        )
        return
    if not complete_bracket_visible(
        venue,
        stop_oid=context.stop_oid,
        target_oid=ack.oid,
        position_size_signed=context.position_size_signed,
        target_price=context.target_price,
    ):
        _fault(events, SolOrderRestartError("recovered target bracket mismatch"))
    machine.confirm_target(target_oid=ack.oid)
    events.emit_reconciliation(venue)
    events.emit_state()


def _restore_pending_target(
    records: list[dict[str, object]],
    pending: PendingSolOrderIntent,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
) -> PendingPositionContext:
    try:
        context = pending_position_context_for_intent(
            records,
            "TARGET_PENDING",
            pending.client_order_id,
        )
    except SolOrderRestartError as exc:
        _fault(events, exc)
    if context.stop_oid is None or context.target_price is None:
        _fault(events, SolOrderRestartError("pending target lacks stop or price"))
    if context.execution_plan is None:
        _fault(events, SolOrderRestartError("pending target lacks execution plan"))
    machine.restore_target_pending(
        entry_oid=context.entry_oid,
        stop_oid=context.stop_oid,
        position_size_signed=context.position_size_signed,
        opened_at_ms=context.opened_at_ms,
        target_price=context.target_price,
        execution_plan=context.execution_plan,
        protective_progress=context.protective_progress,
    )
    events.emit_state()
    return context


def _recover_ack(
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    pending: PendingSolOrderIntent,
) -> HyperliquidOrderAck:
    try:
        return orders.recover_existing_intent(
            operation="target",
            client_order_id=pending.client_order_id,
        )
    except SolOrderRecoveryError as exc:
        raise SolLiveEngineError(str(exc)) from exc
    except SolOrderSubmissionError as exc:
        _fault(events, exc)


def _complete_flat_target(
    *,
    adapter: SolLiveAdapterProtocol,
    events: SolLiveEngineEvents,
    machine: SolLiveStateMachine,
    orders: SolOrderSubmission,
    venue: SolReconciliationSnapshot,
    stop_oid: int,
    target_oid: int,
    position_size_signed: float,
) -> None:
    reason = owned_exit_reason(
        venue,
        stop_oid=stop_oid,
        target_oid=target_oid,
        position_size_signed=position_size_signed,
        protective_progress=machine.snapshot.protective_progress,
    )
    if reason != "target":
        _fault(events, SolOrderRestartError("recovered target fill is not exact"))
    owned = {stop_oid, target_oid}
    if any(order.oid not in owned for order in venue.open_orders):
        _fault(events, SolOrderRestartError("target recovery found unknown order"))
    for order in venue.open_orders:
        cancel = orders.cancel_order(order.oid)
        events.emit_ack("target_restart_residual_cancel", cancel)
        if not cancel.accepted:
            _fault(events, SolOrderRestartError("target residual cancel failed"))
    after = adapter.reconcile()
    if not after.is_flat:
        _fault(events, SolOrderRestartError("target recovery did not reach flat"))
    events.emit_reconciliation(after)
    events.confirm_target_fill_during_protection(target_oid=target_oid)


def _fault(events: SolLiveEngineEvents, error: Exception) -> NoReturn:
    reason = str(error)
    events.fault(reason)
    raise SolLiveEngineError(reason) from error
