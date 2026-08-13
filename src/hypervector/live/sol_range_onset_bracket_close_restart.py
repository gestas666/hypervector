"""Crash recovery for stop-preserving target-bracket closes."""

from __future__ import annotations

from typing import Literal, NoReturn

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolReconciliationSnapshot,
)
from hypervector.live.sol_order_restart import PendingSolOrderIntent
from hypervector.live.sol_order_restart_context import PendingPositionContext
from hypervector.live.sol_order_submission import (
    SolOrderRecoveryError,
    SolOrderSubmission,
    SolOrderSubmissionError,
)
from hypervector.live.sol_range_onset_bracket import complete_bracket_visible
from hypervector.live.sol_range_onset_bracket_close import (
    restore_target_after_close_failure,
)
from hypervector.live.sol_range_onset_bracket_exit import (
    reconcile_owned_bracket_exit,
)
from hypervector.live.sol_range_onset_consistency import (
    SolReconciliationPoller,
    protected_order_visible,
)
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_state import SolLiveStateMachine

BracketExitRestartDisposition = Literal["complete", "resume_unprotected"]


def recover_bracket_exit(
    *,
    context: PendingPositionContext,
    events: SolLiveEngineEvents,
    machine: SolLiveStateMachine,
    orders: SolOrderSubmission,
    pending: PendingSolOrderIntent | None,
    poller: SolReconciliationPoller,
    venue: SolReconciliationSnapshot,
) -> BracketExitRestartDisposition:
    """Recover one interrupted bracket close without duplicating its mutation."""
    stop_oid, target_oid, target_price = _required_identity(context, events)
    if venue.position.size_signed != 0.0 and not venue.open_orders:
        return "resume_unprotected"
    machine.restore_exit_pending(
        entry_oid=context.entry_oid,
        stop_oid=stop_oid,
        position_size_signed=context.position_size_signed,
        opened_at_ms=context.opened_at_ms,
        execution_plan=context.execution_plan,
        target_oid=target_oid,
        target_price=target_price,
    )
    events.emit_state()
    if pending is None:
        _recover_without_close(
            context=context,
            venue=venue,
            machine=machine,
            events=events,
            orders=orders,
            poller=poller,
        )
        return "complete"
    ack = _recover_close_ack(events, orders, pending)
    events.emit_ack("reduce_only_close_restart_recovery", ack, event_type="close")
    if ack.status in {"canceled", "rejected"}:
        _restore_open_bracket(context, venue, machine, events, orders, poller)
        return "complete"
    _complete_recovered_close(context, venue, ack, machine, events, orders, poller)
    return "complete"


def _recover_without_close(
    *,
    context: PendingPositionContext,
    venue: SolReconciliationSnapshot,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
) -> None:
    if venue.position.size_signed == 0.0:
        _complete_intervening_fill(context, venue, machine, events, orders, poller)
        return
    _restore_open_bracket(context, venue, machine, events, orders, poller)


def _restore_open_bracket(
    context: PendingPositionContext,
    venue: SolReconciliationSnapshot,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
) -> None:
    stop_oid, target_oid, target_price = _required_identity(context, events)
    if complete_bracket_visible(
        venue,
        stop_oid=stop_oid,
        target_oid=target_oid,
        position_size_signed=context.position_size_signed,
        target_price=target_price,
    ):
        machine.restore_protection_after_exit_failure(stop_oid=stop_oid)
        events.emit_reconciliation(venue)
        events.emit_state()
        return
    if not _stop_only_visible(venue, context, stop_oid):
        _fault(events, "bracket close restart is neither bracketed nor stop-only")
    restore_target_after_close_failure(
        snapshot=machine.snapshot,
        venue=venue,
        target_price=target_price,
        machine=machine,
        events=events,
        orders=orders,
        poller=poller,
        failure="interrupted close",
    )


def _complete_recovered_close(
    context: PendingPositionContext,
    venue: SolReconciliationSnapshot,
    ack: HyperliquidOrderAck,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
) -> None:
    if not ack.accepted or ack.oid is None or ack.status != "filled":
        _fault(events, "recovered bracket close is unresolved")
    after_close = venue
    if after_close.position.size_signed != 0.0:
        after_close = poller.wait_for(
            lambda current: current.position.size_signed == 0.0
        )
    if after_close.position.size_signed != 0.0:
        _fault(events, "recovered bracket close retains venue exposure")
    _cancel_owned_residuals(context, after_close, orders, events)
    after = poller.wait_for(lambda current: current.is_flat)
    if not after.is_flat:
        _fault(events, "recovered bracket close residual cleanup is not flat")
    machine.acknowledge_close(ack.oid)
    machine.confirm_flat()
    events.emit_close_complete(reason="restart_recovery", oid=ack.oid)
    events.emit_reconciliation(after)
    events.emit_state()


def _complete_intervening_fill(
    context: PendingPositionContext,
    venue: SolReconciliationSnapshot,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
) -> None:
    if not reconcile_owned_bracket_exit(
        snapshot=machine.snapshot,
        venue=venue,
        orders=orders,
        events=events,
        poller=poller,
    ):
        _fault(events, "interrupted bracket fill was not exactly attributable")


def _cancel_owned_residuals(
    context: PendingPositionContext,
    venue: SolReconciliationSnapshot,
    orders: SolOrderSubmission,
    events: SolLiveEngineEvents,
) -> None:
    owned = {context.stop_oid, context.target_oid}
    unknown = [order.oid for order in venue.open_orders if order.oid not in owned]
    if unknown:
        _fault(events, f"recovered bracket close found unknown orders: {unknown}")
    for order in venue.open_orders:
        ack = orders.cancel_order(order.oid)
        events.emit_ack("restart_close_residual_cancel", ack)
        if not ack.accepted:
            _fault(events, f"restart residual cancel rejected: {ack.status}")


def _recover_close_ack(
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    pending: PendingSolOrderIntent,
) -> HyperliquidOrderAck:
    try:
        return orders.recover_existing_intent(
            operation="reduce_only_close",
            client_order_id=pending.client_order_id,
        )
    except SolOrderRecoveryError as exc:
        raise SolLiveEngineError(str(exc)) from exc
    except SolOrderSubmissionError as exc:
        _fault(events, str(exc))


def _stop_only_visible(
    venue: SolReconciliationSnapshot,
    context: PendingPositionContext,
    stop_oid: int,
) -> bool:
    return {order.oid for order in venue.open_orders} == {stop_oid} and (
        protected_order_visible(
            venue,
            stop_oid=stop_oid,
            position_size_signed=context.position_size_signed,
        )
    )


def _required_identity(
    context: PendingPositionContext,
    events: SolLiveEngineEvents,
) -> tuple[int, int, float]:
    if context.stop_oid is None:
        _fault(events, "bracket exit restart lacks stop ownership")
    if context.target_oid is None or context.target_price is None:
        _fault(events, "bracket exit restart lacks target ownership")
    return context.stop_oid, context.target_oid, context.target_price


def _fault(events: SolLiveEngineEvents, reason: str) -> NoReturn:
    events.fault(reason)
    raise SolLiveEngineError(reason)
