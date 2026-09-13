"""Require fresh exact-order evidence before resuming a timed-out cancellation."""

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolReconciliationSnapshot,
)
from hypervector.live.sol_cancel_restart_context import CancelFaultContext
from hypervector.live.sol_order_restart import SolOrderRestartError
from hypervector.live.sol_order_submission import SolOrderSubmission
from hypervector.live.sol_range_onset_consistency import SolReconciliationPoller
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_startup_support import _fault_and_raise


def reconcile_cancel_fault(
    context: CancelFaultContext,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
    events: SolLiveEngineEvents,
) -> SolReconciliationSnapshot:
    """Read the original OID without canceling again; reject inconsistent visibility."""
    ack = orders.recover_existing_cancel(context.oid)
    if ack.status not in {"canceled", "open", "filled"}:
        _fault_and_raise(
            events, SolOrderRestartError(f"cancel restart status is unresolved: {ack.status}")
        )
    venue = poller.wait_for(lambda current: _consistent(ack, current))
    if not _consistent(ack, venue):
        _fault_and_raise(
            events,
            SolOrderRestartError("cancel restart status disagrees with venue orders or fills"),
        )
    events.emit_ack("cancel_restart_recovery", ack)
    events.emit_reconciliation(venue)
    return venue


def _consistent(ack: HyperliquidOrderAck, venue: SolReconciliationSnapshot) -> bool:
    present = any(order.oid == ack.oid for order in venue.open_orders)
    if ack.status == "open":
        return present
    if ack.status == "canceled":
        return not present
    return not present and any(fill.oid == ack.oid for fill in venue.fills)
