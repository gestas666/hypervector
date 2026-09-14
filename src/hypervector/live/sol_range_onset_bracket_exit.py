"""Continuous cleanup of exact stop and target fills for an OPEN position."""

from __future__ import annotations

import math
from typing import NoReturn

from hypervector.live.hyperliquid_protocol import SolOpenOrder, SolReconciliationSnapshot
from hypervector.live.sol_execution_evidence import QUANTITY_TOLERANCE
from hypervector.live.sol_order_submission import SolOrderSubmission
from hypervector.live.sol_range_onset_bracket import owned_exit_reason
from hypervector.live.sol_range_onset_consistency import SolReconciliationPoller
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_state import SolLiveSnapshot


def reconcile_owned_bracket_exit(
    *,
    snapshot: SolLiveSnapshot,
    venue: SolReconciliationSnapshot,
    orders: SolOrderSubmission,
    events: SolLiveEngineEvents,
    poller: SolReconciliationPoller,
) -> SolReconciliationSnapshot | None:
    """Return the final owned-exit snapshot after verified sibling cleanup, if applicable."""
    if venue.position.size_signed != 0.0:
        return None
    if snapshot.target_oid is None:
        return None
    if snapshot.stop_oid is None:
        _fault(events, "open flat reconciliation lacks stop ownership")
    reason = owned_exit_reason(
        venue,
        stop_oid=snapshot.stop_oid,
        target_oid=snapshot.target_oid,
        position_size_signed=snapshot.position_size_signed,
        protective_progress=snapshot.protective_progress,
    )
    if reason is None:
        _fault(events, "flat reconciliation lacks a complete owned exit fill")
    owned = {snapshot.stop_oid, snapshot.target_oid}
    unknown = [order.oid for order in venue.open_orders if order.oid not in owned]
    if unknown:
        _fault(events, f"flat reconciliation contains unknown orders: {unknown}")
    for order in venue.open_orders:
        if _original_order_filled(order, venue, snapshot.position_size_signed):
            continue
        ack = orders.cancel_order(order.oid)
        events.emit_ack("cancel_residual_bracket_after_fill", ack)
        if not ack.accepted:
            _fault(events, f"residual bracket cancel rejected: {ack.status}")
    after = poller.wait_for(lambda current: current.is_flat)
    if not after.is_flat:
        _fault(events, "residual bracket cleanup did not reconcile flat")
    events.emit_reconciliation(after)
    events.confirm_owned_bracket_exit(
        reason=reason,
        owned_oids=tuple(sorted(owned)),
    )
    return after


def _original_order_filled(
    order: SolOpenOrder, venue: SolReconciliationSnapshot, position_size_signed: float
) -> bool:
    """A complete original quantity is executed even if its open-order receipt is stale."""
    side = "A" if position_size_signed > 0.0 else "B"
    direction = "close long" if position_size_signed > 0.0 else "close short"
    filled = sum(
        fill.size
        for fill in venue.fills
        if fill.oid == order.oid
        and fill.side == side
        and fill.direction.strip().lower() == direction
    )
    return (
        order.reduce_only
        and order.side == side
        and order.original_size > 0.0
        and math.isclose(filled, order.original_size, rel_tol=0.0, abs_tol=QUANTITY_TOLERANCE)
    )


def _fault(events: SolLiveEngineEvents, reason: str) -> NoReturn:
    events.fault(reason)
    raise SolLiveEngineError(reason)
