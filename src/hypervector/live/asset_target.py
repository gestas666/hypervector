"""Fail-closed optional target placement for the shared live lifecycle."""

from __future__ import annotations

from typing import NoReturn, Protocol

from hypervector.live.cohort_execution_plan import BoundExecutionPlan
from hypervector.live.hyperliquid_protocol import HyperliquidReconciliationSnapshot
from hypervector.live.asset_order_submission import AssetOrderSubmission
from hypervector.live.asset_bracket import (
    complete_bracket_visible,
    owned_exit_reason,
)
from hypervector.live.asset_consistency import AssetReconciliationPoller
from hypervector.live.asset_engine_contract import AssetLiveEngineError
from hypervector.live.asset_engine_events import AssetLiveEngineEvents
from hypervector.live.asset_state import (
    AssetLiveSnapshot,
    AssetLiveStateMachine,
)


class EmergencyFlattenProtocol(Protocol):
    """Emergency close boundary retained by the owning engine."""

    def __call__(
        self,
        *,
        position_size_signed: float,
        mark_price: float,
        reason: str,
        stop_oid: int | None = None,
    ) -> NoReturn: ...


def complete_entry_protection(
    *,
    plan: BoundExecutionPlan,
    entry_price: float,
    position_size_signed: float,
    stop_oid: int,
    mark_price: float,
    machine: AssetLiveStateMachine,
    events: AssetLiveEngineEvents,
    orders: AssetOrderSubmission,
    poller: AssetReconciliationPoller,
    emergency_flatten: EmergencyFlattenProtocol,
) -> AssetLiveSnapshot:
    """Finish a stop-only position or place and verify its required target."""
    side = "long" if position_size_signed > 0.0 else "short"
    target_price = plan.target_price(entry_price=entry_price, side=side)
    if target_price is None:
        machine.confirm_protection(stop_oid=stop_oid)
        events.emit_state()
        return machine.snapshot
    target_oid, venue = _place_and_poll_target(
        position_size_signed,
        stop_oid,
        target_price,
        mark_price,
        machine,
        events,
        orders,
        poller,
        emergency_flatten,
    )
    if venue.position.size_signed == 0.0:
        return _complete_immediate_target(
            venue=venue,
            stop_oid=stop_oid,
            target_oid=target_oid,
            position_size_signed=position_size_signed,
            machine=machine,
            events=events,
            orders=orders,
            poller=poller,
        )
    return _confirm_resting_target(
        venue, stop_oid, target_oid, position_size_signed, target_price, machine, events
    )


def _confirm_resting_target(
    venue: HyperliquidReconciliationSnapshot,
    stop_oid: int,
    target_oid: int,
    position_size_signed: float,
    target_price: float,
    machine: AssetLiveStateMachine,
    events: AssetLiveEngineEvents,
) -> AssetLiveSnapshot:
    if not complete_bracket_visible(
        venue,
        stop_oid=stop_oid,
        target_oid=target_oid,
        position_size_signed=position_size_signed,
        target_price=target_price,
    ):
        reason = "target acknowledged but complete bracket is not venue-visible"
        events.fault(reason)
        raise AssetLiveEngineError(reason)
    machine.confirm_target(target_oid=target_oid)
    events.emit_reconciliation(venue)
    events.emit_state()
    return machine.snapshot


def _place_and_poll_target(
    position_size_signed: float,
    stop_oid: int,
    target_price: float,
    mark_price: float,
    machine: AssetLiveStateMachine,
    events: AssetLiveEngineEvents,
    orders: AssetOrderSubmission,
    poller: AssetReconciliationPoller,
    emergency_flatten: EmergencyFlattenProtocol,
) -> tuple[int, HyperliquidReconciliationSnapshot]:
    machine.begin_target(stop_oid=stop_oid, target_price=target_price)
    events.emit_state()
    ack = orders.place_target(
        position_size_signed=position_size_signed,
        limit_price=target_price,
    )
    events.emit_ack("target", ack, event_type="target_order")
    if not ack.accepted or ack.oid is None:
        emergency_flatten(
            position_size_signed=position_size_signed,
            mark_price=mark_price,
            reason=f"target rejected: {ack.error or ack.status}",
            stop_oid=stop_oid,
        )
    venue = poller.wait_for(
        lambda current: current.position.size_signed == 0.0
        or complete_bracket_visible(
            current,
            stop_oid=stop_oid,
            target_oid=ack.oid,
            position_size_signed=position_size_signed,
            target_price=target_price,
        )
    )
    return ack.oid, venue


def _complete_immediate_target(
    *,
    venue: HyperliquidReconciliationSnapshot,
    stop_oid: int,
    target_oid: int,
    position_size_signed: float,
    machine: AssetLiveStateMachine,
    events: AssetLiveEngineEvents,
    orders: AssetOrderSubmission,
    poller: AssetReconciliationPoller,
) -> AssetLiveSnapshot:
    reason = owned_exit_reason(
        venue,
        stop_oid=stop_oid,
        target_oid=target_oid,
        position_size_signed=position_size_signed,
        protective_progress=machine.snapshot.protective_progress,
    )
    if reason != "target":
        events.fault("flat during target placement lacks exact target fill")
        raise AssetLiveEngineError("flat during target placement lacks exact target fill")
    _cancel_owned_residuals(venue, {stop_oid, target_oid}, orders, events)
    after = poller.wait_for(lambda current: current.is_flat)
    if not after.is_flat:
        events.fault("target fill residual order cleanup did not reconcile flat")
        raise AssetLiveEngineError("target fill cleanup did not reconcile flat")
    events.emit_reconciliation(after)
    events.confirm_target_fill_during_protection(target_oid=target_oid)
    return machine.snapshot


def _cancel_owned_residuals(
    venue: HyperliquidReconciliationSnapshot,
    owned: set[int],
    orders: AssetOrderSubmission,
    events: AssetLiveEngineEvents,
) -> None:
    unknown = [order.oid for order in venue.open_orders if order.oid not in owned]
    if unknown:
        events.fault(f"flat target reconciliation contains unknown orders: {unknown}")
        raise AssetLiveEngineError("flat target reconciliation contains unknown orders")
    for order in venue.open_orders:
        ack = orders.cancel_order(order.oid)
        events.emit_ack("cancel_residual_bracket", ack)
        if not ack.accepted:
            events.fault("residual bracket cancellation failed")
            raise AssetLiveEngineError("residual bracket cancellation failed")
