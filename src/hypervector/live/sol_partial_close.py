"""Persist only an exact owned partial close under sufficient existing protection."""

from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.sol_execution_evidence import partial_close_size
from hypervector.live.sol_protective_order import protective_stop_covers
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_state import SolLiveStateMachine


def acknowledge_protected_partial_close(
    *,
    venue: SolReconciliationSnapshot,
    close_oid: int,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
) -> bool:
    """Retain the exact remainder only when its owned stop is the sole covering order."""
    before = machine.snapshot
    remaining = partial_close_size(before, venue, close_oid)
    if remaining is None or len(venue.open_orders) != 1:
        return False
    stop = venue.open_orders[0]
    if stop.oid != before.stop_oid or not protective_stop_covers(stop, remaining):
        return False
    machine.acknowledge_partial_close(position_size_signed=remaining)
    events.emit_reconciliation(venue)
    events.emit_state()
    events.emit(
        "close",
        {
            "oid": close_oid,
            "partial": True,
            "verified_flat": False,
            "closed_quantity": abs(before.position_size_signed) - abs(remaining),
            "remaining_size_signed": remaining,
        },
    )
    return True
