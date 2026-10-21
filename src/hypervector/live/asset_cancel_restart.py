"""Require fresh exact-order evidence before resuming a timed-out cancellation."""

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidReconciliationSnapshot,
)
from hypervector.live.asset_cancel_restart_context import CancelFaultContext
from hypervector.live.asset_order_restart import AssetOrderRestartError
from hypervector.live.asset_order_submission import AssetOrderSubmission
from hypervector.live.asset_consistency import AssetReconciliationPoller
from hypervector.live.asset_engine_events import AssetLiveEngineEvents
from hypervector.live.asset_startup_support import _fault_and_raise


def reconcile_cancel_fault(
    context: CancelFaultContext,
    orders: AssetOrderSubmission,
    poller: AssetReconciliationPoller,
    events: AssetLiveEngineEvents,
) -> HyperliquidReconciliationSnapshot:
    """Read the original OID without canceling again; reject inconsistent visibility."""
    ack = orders.recover_existing_cancel(context.oid)
    if ack.status not in {"canceled", "open", "filled"}:
        _fault_and_raise(
            events, AssetOrderRestartError(f"cancel restart status is unresolved: {ack.status}")
        )
    venue = poller.wait_for(lambda current: _consistent(ack, current))
    if not _consistent(ack, venue):
        _fault_and_raise(
            events,
            AssetOrderRestartError("cancel restart status disagrees with venue orders or fills"),
        )
    events.emit_ack("cancel_restart_recovery", ack)
    events.emit_reconciliation(venue)
    return venue


def _consistent(ack: HyperliquidOrderAck, venue: HyperliquidReconciliationSnapshot) -> bool:
    present = any(order.oid == ack.oid for order in venue.open_orders)
    if ack.status == "open":
        return present
    if ack.status == "canceled":
        return not present
    return not present and any(fill.oid == ack.oid for fill in venue.fills)
