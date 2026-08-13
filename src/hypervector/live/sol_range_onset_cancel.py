"""Exact protective-stop cancellation with ambiguous-response recovery."""

from __future__ import annotations

from dataclasses import dataclass

from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.sol_order_submission import SolOrderSubmission
from hypervector.live.sol_range_onset_consistency import SolReconciliationPoller
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_reconcile import (
    RecoveredSolOwnership,
    owned_protective_stop_fill,
)
from hypervector.live.sol_range_onset_state import SolLiveSnapshot


@dataclass(frozen=True)
class SolCancelResolution:
    """Authoritative venue state after exact native-stop cancellation."""

    venue: SolReconciliationSnapshot
    flattened: bool


def cancel_owned_stop(
    *,
    orders: SolOrderSubmission,
    events: SolLiveEngineEvents,
    poller: SolReconciliationPoller,
    local: SolLiveSnapshot,
    before: SolReconciliationSnapshot,
    stop_oid: int,
) -> SolCancelResolution:
    """Cancel one stop and reconcile any ambiguous response before closing."""
    cancel = orders.cancel_order(stop_oid)
    events.emit_ack("protective_stop_cancel", cancel)
    venue = before
    if cancel.recovered_after_transport_error:
        venue = poller.wait_for(
            lambda snapshot: snapshot.is_flat
            or all(order.oid != stop_oid for order in snapshot.open_orders)
        )
        if venue.is_flat:
            _confirm_stop_fill(events, local, venue, stop_oid)
            return SolCancelResolution(venue, True)
        if any(order.oid == stop_oid for order in venue.open_orders):
            _fault(events, "protective stop cancel did not become venue-visible")
    if not cancel.accepted and cancel.status != "filled":
        detail = cancel.error or cancel.status
        _fault(events, f"protective stop cancel rejected: {detail}")
    return SolCancelResolution(venue, False)


def _confirm_stop_fill(
    events: SolLiveEngineEvents,
    local: SolLiveSnapshot,
    venue: SolReconciliationSnapshot,
    stop_oid: int,
) -> None:
    if local.entry_oid is None or local.opened_at_ms is None:
        _fault(events, "cancel reconciliation lacks local ownership identity")
    ownership = RecoveredSolOwnership(
        entry_oid=local.entry_oid,
        stop_oid=stop_oid,
        position_size_signed=local.position_size_signed,
        opened_at_ms=local.opened_at_ms,
    )
    if not owned_protective_stop_fill(ownership, venue):
        _fault(events, "cancel reconciliation reported unexplained flat state")
    events.emit_reconciliation(venue)
    events.confirm_stop_fill_during_exit(
        stop_oid=stop_oid,
        reason="protective_stop_during_exit",
    )


def _fault(events: SolLiveEngineEvents, reason: str) -> None:
    events.fault(reason)
    raise SolLiveEngineError(reason)
