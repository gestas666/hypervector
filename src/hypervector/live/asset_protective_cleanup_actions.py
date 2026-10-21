"""Complete only owned cancellations after a receipt-proven protective exit."""

from hypervector.live.hyperliquid_protocol import HyperliquidReconciliationSnapshot
from hypervector.live.asset_live_snapshot import AssetLiveSnapshot
from hypervector.live.asset_order_submission import AssetOrderSubmission
from hypervector.live.asset_protective_checkpoint import venue_without_credited_fills
from hypervector.live.asset_protective_cleanup_checkpoint import CLEANUP_UNRESOLVED
from hypervector.live.asset_protective_execution_evidence import (
    ProtectiveExecutionProgress,
)
from hypervector.live.asset_bracket_close import _cancel_residual_orders
from hypervector.live.asset_consistency import AssetReconciliationPoller
from hypervector.live.asset_engine_events import AssetLiveEngineEvents
from hypervector.live.asset_reconcile import AssetStartupReconciliationError


def finish_protective_cleanup(
    *,
    owner: AssetLiveSnapshot,
    completed: ProtectiveExecutionProgress,
    venue: HyperliquidReconciliationSnapshot,
    orders: AssetOrderSubmission,
    events: AssetLiveEngineEvents,
    poller: AssetReconciliationPoller,
    resuming: bool,
    completion_recorded: bool = False,
) -> HyperliquidReconciliationSnapshot:
    """Avoid another close and distinguish already-terminal cancels from orders still resting."""
    _require_completed_venue(owner, completed, venue)
    if resuming:
        _recover_remaining_cancels(venue, orders, events)
    else:
        _cancel_residual_orders(venue, {owner.stop_oid, owner.target_oid}, orders, events)
    after = poller.wait_for(lambda current: current.is_flat)
    _require_completed_venue(owner, completed, after)
    if not after.is_flat:
        raise AssetStartupReconciliationError(CLEANUP_UNRESOLVED)
    events.emit_reconciliation(after)
    if completion_recorded:
        events.confirm_recorded_owned_exit()
    else:
        events.confirm_owned_bracket_exit(
            reason="protective_stop_remainder",
            owned_oids=tuple(sorted({fill.oid for fill in completed.fills})),
        )
    return after


def _recover_remaining_cancels(
    venue: HyperliquidReconciliationSnapshot, orders: AssetOrderSubmission, events: AssetLiveEngineEvents
) -> None:
    for order in venue.open_orders:
        status = orders.recover_existing_cancel(order.oid)
        events.emit_ack("protective_cleanup_status", status)
        if status.oid != order.oid:
            raise AssetStartupReconciliationError("cleanup lookup changed its owned order identity")
        if status.status in {"canceled", "filled"}:
            continue
        if status.status != "open":
            raise AssetStartupReconciliationError(CLEANUP_UNRESOLVED)
        ack = orders.cancel_order(order.oid)
        events.emit_ack("cancel_residual_after_close", ack)
        if not ack.accepted:
            raise AssetStartupReconciliationError(CLEANUP_UNRESOLVED)


def _require_completed_venue(
    owner: AssetLiveSnapshot, completed: ProtectiveExecutionProgress, venue: HyperliquidReconciliationSnapshot
) -> None:
    remaining = venue_without_credited_fills(venue, completed)
    exit_oids = {fill.oid for fill in completed.fills}
    ids = [order.oid for order in venue.open_orders]
    if (
        venue.position.size_signed != 0.0
        or len(ids) != len(set(ids))
        or not set(ids).issubset({owner.stop_oid, owner.target_oid})
        or any(
            not order.reduce_only or order.side != ("A" if owner.position_size_signed > 0 else "B")
            for order in venue.open_orders
        )
        or any(fill.oid in exit_oids for fill in remaining.fills)
    ):
        raise AssetStartupReconciliationError(
            "protective cleanup venue contradicts verified completion"
        )
