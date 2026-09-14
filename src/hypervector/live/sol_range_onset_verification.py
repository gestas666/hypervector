"""Shared ownership verification for stop-only and bracketed positions."""

from __future__ import annotations

import math
from collections.abc import Callable

from hypervector.live.cohort_execution_plan import BoundExecutionPlan
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolReconciliationSnapshot,
)
from hypervector.live.sol_execution_evidence import (
    QUANTITY_TOLERANCE,
    owned_fill_quantity,
)
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_reconcile import reconcile_sol_startup
from hypervector.live.sol_range_onset_state import SolLiveSnapshot
from hypervector.live.sol_protective_execution_evidence import (
    ProtectiveExecutionProgress,
)


def verify_canceled_entry_exposure(
    ack: HyperliquidOrderAck,
    venue: SolReconciliationSnapshot,
    fault: Callable[[str], None],
) -> None:
    """Recheck the current canceled-entry fill attribution immediately before protection."""
    if ack.status != "canceled":
        return
    if not _canceled_entry_matches(ack, venue):
        reason = "canceled entry fill evidence conflicts with current exposure"
        fault(reason)
        raise SolLiveEngineError(reason)


def _canceled_entry_matches(ack: HyperliquidOrderAck, venue: SolReconciliationSnapshot) -> bool:
    if not ack.accepted or ack.oid is None or ack.venue_timestamp_ms is None:
        return False
    size = venue.position.size_signed
    quantity = owned_fill_quantity(
        venue,
        ack.oid,
        position_size_signed=size,
        entering=True,
        earliest_ms=0,
        latest_ms=ack.venue_timestamp_ms,
    )
    return (
        not venue.open_orders
        and quantity is not None
        and ack.filled_size is not None
        and math.isclose(quantity, ack.filled_size, rel_tol=0.0, abs_tol=QUANTITY_TOLERANCE)
        and math.isclose(quantity, abs(size), rel_tol=0.0, abs_tol=QUANTITY_TOLERANCE)
    )


def verify_protected_position(
    *,
    entry_oid: int,
    stop_oid: int,
    position_size_signed: float,
    opened_at_ms: int | None,
    venue: SolReconciliationSnapshot,
    target_oid: int | None = None,
    target_price: float | None = None,
    execution_plan: BoundExecutionPlan | None = None,
    protective_progress: ProtectiveExecutionProgress = ProtectiveExecutionProgress(),
) -> bool:
    """Return whether exact ownership resolved as an already-filled stop."""
    result = reconcile_sol_startup(
        records=[
            {
                "event_type": "state_transition",
                "payload": {
                    "state": "OPEN",
                    "entry_oid": entry_oid,
                    "stop_oid": stop_oid,
                    "target_oid": target_oid,
                    "target_price": target_price,
                    "position_size_signed": position_size_signed,
                    "opened_at_ms": opened_at_ms,
                    "protective_progress": protective_progress.as_payload(),
                    "execution_plan": (
                        execution_plan.as_payload() if execution_plan is not None else None
                    ),
                },
            }
        ],
        venue=venue,
    )
    return result.disposition == "protective_stop_filled"


def verify_open_snapshot(
    snapshot: SolLiveSnapshot,
    venue: SolReconciliationSnapshot,
) -> bool:
    """Verify all exact order identities attached to one OPEN snapshot."""
    if snapshot.entry_oid is None or snapshot.stop_oid is None:
        raise SolLiveEngineError("open state lacks owned order identity")
    return verify_protected_position(
        entry_oid=snapshot.entry_oid,
        stop_oid=snapshot.stop_oid,
        target_oid=snapshot.target_oid,
        target_price=snapshot.target_price,
        position_size_signed=snapshot.position_size_signed,
        opened_at_ms=snapshot.opened_at_ms,
        execution_plan=snapshot.execution_plan,
        protective_progress=snapshot.protective_progress,
        venue=venue,
    )
