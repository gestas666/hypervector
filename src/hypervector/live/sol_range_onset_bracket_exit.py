"""Continuous cleanup of exact stop and target fills for an OPEN position."""

from __future__ import annotations

from typing import NoReturn

from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
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
) -> bool:
    """Clean exact residual siblings and transition an owned close to FLAT."""
    if venue.position.size_signed != 0.0:
        return False
    if snapshot.target_oid is None:
        return False
    if snapshot.stop_oid is None:
        _fault(events, "open flat reconciliation lacks stop ownership")
    reason = owned_exit_reason(
        venue,
        stop_oid=snapshot.stop_oid,
        target_oid=snapshot.target_oid,
        position_size_signed=snapshot.position_size_signed,
    )
    if reason is None:
        _fault(events, "flat reconciliation lacks a complete owned exit fill")
    owned = {snapshot.stop_oid}
    if snapshot.target_oid is not None:
        owned.add(snapshot.target_oid)
    unknown = [order.oid for order in venue.open_orders if order.oid not in owned]
    if unknown:
        _fault(events, f"flat reconciliation contains unknown orders: {unknown}")
    for order in venue.open_orders:
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
    return True


def _fault(events: SolLiveEngineEvents, reason: str) -> NoReturn:
    events.fault(reason)
    raise SolLiveEngineError(reason)
