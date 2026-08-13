"""Scheduled close lifecycle for a stop-only protected position."""

from __future__ import annotations

from typing import Protocol

from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.sol_order_submission import SolOrderSubmission
from hypervector.live.sol_range_onset_cancel import cancel_owned_stop
from hypervector.live.sol_range_onset_consistency import SolReconciliationPoller
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_state import (
    SolLiveSnapshot,
    SolLiveStateMachine,
)


class ReprotectAfterCloseFailure(Protocol):
    """Callable boundary for restoring a stop after close failure."""

    def __call__(
        self,
        venue: SolReconciliationSnapshot,
        prior_trigger_price: float | None,
    ) -> bool:
        """Return whether the remaining position was safely reprotected."""
        ...


def close_stop_only_position(
    *,
    snapshot: SolLiveSnapshot,
    venue: SolReconciliationSnapshot,
    mark_price: float,
    reason: str,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
    reprotect: ReprotectAfterCloseFailure,
) -> SolLiveSnapshot:
    """Cancel the exact stop, close reduce-only, and verify venue flat."""
    stop_oid = snapshot.stop_oid
    if stop_oid is None:
        events.fault("open position has no stop oid")
        raise SolLiveEngineError("open position has no stop oid")
    stop_order = next(order for order in venue.open_orders if order.oid == stop_oid)
    events.emit_close_intent(reason=reason, stop_oid=stop_oid)
    machine.begin_exit()
    events.emit_state()
    canceled = cancel_owned_stop(
        orders=orders,
        events=events,
        poller=poller,
        local=machine.snapshot,
        before=venue,
        stop_oid=stop_oid,
    )
    if canceled.flattened:
        return machine.snapshot
    return _submit_and_verify_close(
        venue=canceled.venue,
        mark_price=mark_price,
        reason=reason,
        trigger_price=stop_order.trigger_price,
        machine=machine,
        events=events,
        orders=orders,
        poller=poller,
        reprotect=reprotect,
    )


def _submit_and_verify_close(
    *,
    venue: SolReconciliationSnapshot,
    mark_price: float,
    reason: str,
    trigger_price: float | None,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
    reprotect: ReprotectAfterCloseFailure,
) -> SolLiveSnapshot:
    close = orders.close_position(
        position_size_signed=venue.position.size_signed,
        mark_price=mark_price,
    )
    events.emit_ack("reduce_only_close", close, event_type="close")
    if not close.accepted or close.oid is None:
        if reprotect(venue, trigger_price):
            return machine.snapshot
        failure = f"reduce-only close rejected: {close.error or close.status}"
        events.fault(failure)
        raise SolLiveEngineError(failure)
    machine.acknowledge_close(close.oid)
    after = poller.wait_for(lambda current: current.is_flat)
    if not after.is_flat:
        if reprotect(after, trigger_price):
            return machine.snapshot
        failure = "reduce-only close acknowledged but venue did not reconcile flat"
        events.fault(failure)
        raise SolLiveEngineError(failure)
    machine.confirm_flat()
    events.emit_close_complete(reason=reason, oid=close.oid)
    events.emit_reconciliation(after)
    events.emit_state()
    return machine.snapshot
