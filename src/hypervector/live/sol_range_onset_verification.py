"""Shared ownership verification for stop-only and bracketed positions."""

from __future__ import annotations

from hypervector.live.cohort_execution_plan import BoundExecutionPlan
from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_reconcile import reconcile_sol_startup
from hypervector.live.sol_range_onset_state import SolLiveSnapshot


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
                    "execution_plan": (
                        execution_plan.as_payload()
                        if execution_plan is not None
                        else None
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
        venue=venue,
    )
