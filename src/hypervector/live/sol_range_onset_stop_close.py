"""Stop-preserving close lifecycle for a stop-only protected position."""

from __future__ import annotations

import math
from typing import Protocol

from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.sol_order_submission import SolOrderSubmission
from hypervector.live.sol_partial_close import acknowledge_protected_partial_close
from hypervector.live.sol_range_onset_consistency import (
    SolReconciliationPoller,
    protected_order_visible,
)
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_reconcile import (
    RecoveredSolOwnership,
    owned_protective_stop_fill,
)
from hypervector.live.sol_range_onset_state import (
    SolLiveSnapshot,
    SolLiveStateMachine,
)


class RestoreMissingProtection(Protocol):
    """Callable boundary for restoring unexpectedly missing protection."""

    def __call__(
        self,
        venue: SolReconciliationSnapshot,
        prior_trigger_price: float | None,
    ) -> bool:
        """Return whether remaining exposure is venue-protected or flat."""
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
    restore_missing_protection: RestoreMissingProtection,
) -> SolLiveSnapshot:
    """Close reduce-only with the stop armed, then verify venue flat."""
    stop_oid = snapshot.stop_oid
    if stop_oid is None:
        events.fault("open position has no stop oid")
        raise SolLiveEngineError("open position has no stop oid")
    _require_stop_only(venue, snapshot, events)
    stop_order = next(order for order in venue.open_orders if order.oid == stop_oid)
    events.emit_close_intent(reason=reason, stop_oid=stop_oid)
    machine.begin_exit()
    events.emit_state()
    return _submit_and_verify_close(
        snapshot=snapshot,
        venue=venue,
        mark_price=mark_price,
        reason=reason,
        machine=machine,
        events=events,
        orders=orders,
        poller=poller,
        trigger_price=stop_order.trigger_price,
        restore_missing_protection=restore_missing_protection,
    )


def _submit_and_verify_close(
    *,
    snapshot: SolLiveSnapshot,
    venue: SolReconciliationSnapshot,
    mark_price: float,
    reason: str,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
    trigger_price: float | None,
    restore_missing_protection: RestoreMissingProtection,
) -> SolLiveSnapshot:
    close = orders.close_position(
        position_size_signed=venue.position.size_signed,
        mark_price=mark_price,
    )
    events.emit_ack("reduce_only_close", close, event_type="close")
    if not close.accepted or close.oid is None:
        return _reconcile_rejected_close(
            snapshot=snapshot,
            machine=machine,
            events=events,
            poller=poller,
            trigger_price=trigger_price,
            restore_missing_protection=restore_missing_protection,
        )
    machine.acknowledge_close(close.oid)
    after_close = poller.wait_for_close(machine.snapshot, close.oid)
    if after_close.position.size_signed != 0.0:
        if acknowledge_protected_partial_close(
            venue=after_close, close_oid=close.oid, machine=machine, events=events
        ):
            machine.restore_protection_after_exit_failure(stop_oid=snapshot.stop_oid or 0)
            events.emit_state()
            return machine.snapshot
        if not after_close.open_orders and restore_missing_protection(after_close, trigger_price):
            return machine.snapshot
        _fault(events, "close acknowledged but protected exposure remains")
    return _finish_full_close(
        after_close, snapshot, close.oid, reason, machine, events, orders, poller
    )


def _finish_full_close(
    after_close: SolReconciliationSnapshot,
    snapshot: SolLiveSnapshot,
    close_oid: int,
    reason: str,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
) -> SolLiveSnapshot:
    after = cancel_residual_stop_after_close(
        venue=after_close,
        stop_oid=snapshot.stop_oid or 0,
        events=events,
        orders=orders,
        poller=poller,
    )
    if not after.is_flat:
        _fault(events, "post-close residual stop cleanup did not reconcile flat")
    machine.confirm_flat()
    events.emit_close_complete(reason=reason, oid=close_oid)
    events.emit_reconciliation(after)
    events.emit_state()
    return machine.snapshot


def _reconcile_rejected_close(
    *,
    snapshot: SolLiveSnapshot,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
    poller: SolReconciliationPoller,
    trigger_price: float | None,
    restore_missing_protection: RestoreMissingProtection,
) -> SolLiveSnapshot:
    stop_oid = snapshot.stop_oid or 0
    after = poller.wait_for(
        lambda current: current.position.size_signed == 0.0
        or protected_order_visible(
            current,
            stop_oid=stop_oid,
            position_size_signed=snapshot.position_size_signed,
        )
    )
    if after.position.size_signed == 0.0:
        ownership = RecoveredSolOwnership(
            entry_oid=snapshot.entry_oid or 0,
            stop_oid=stop_oid,
            position_size_signed=snapshot.position_size_signed,
            opened_at_ms=snapshot.opened_at_ms or 0,
            protective_progress=snapshot.protective_progress,
        )
        if not owned_protective_stop_fill(ownership, after):
            _fault(events, "rejected close reconciled unexplained flat state")
        events.emit_reconciliation(after)
        events.confirm_stop_fill_during_exit(
            stop_oid=stop_oid,
            reason="protective_stop_during_rejected_exit",
        )
        return machine.snapshot
    if not math.isclose(
        after.position.size_signed,
        snapshot.position_size_signed,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        _fault(events, "rejected close changed position; execution evidence required")
    if not after.open_orders and restore_missing_protection(after, trigger_price):
        return machine.snapshot
    _require_stop_only(after, snapshot, events)
    machine.restore_protection_after_exit_failure(stop_oid=stop_oid)
    events.emit_reconciliation(after)
    events.emit_state()
    return machine.snapshot


def cancel_residual_stop_after_close(
    *,
    venue: SolReconciliationSnapshot,
    stop_oid: int,
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
) -> SolReconciliationSnapshot:
    """Cancel only the owned residual stop after exposure is venue-flat."""
    if venue.position.size_signed != 0.0:
        _fault(events, "residual stop cleanup requires a flat position")
    unknown = [order.oid for order in venue.open_orders if order.oid != stop_oid]
    if unknown:
        _fault(events, f"stop-only close found unknown orders: {unknown}")
    if not venue.open_orders:
        return venue
    cancel = orders.cancel_order(stop_oid)
    events.emit_ack("cancel_residual_after_close", cancel)
    if not cancel.accepted and cancel.status != "filled":
        _fault(events, f"residual stop cancel rejected: {cancel.status}")
    return poller.wait_for(lambda current: current.is_flat)


def _require_stop_only(
    venue: SolReconciliationSnapshot,
    snapshot: SolLiveSnapshot,
    events: SolLiveEngineEvents,
) -> None:
    stop_oid = snapshot.stop_oid or 0
    if {order.oid for order in venue.open_orders} != {stop_oid}:
        _fault(events, "stop-only close requires exactly its owned stop")
    if not protected_order_visible(
        venue,
        stop_oid=stop_oid,
        position_size_signed=snapshot.position_size_signed,
    ):
        _fault(events, "stop-only close protective stop is not venue-visible")


def _fault(events: SolLiveEngineEvents, reason: str) -> None:
    events.fault(reason)
    raise SolLiveEngineError(reason)
