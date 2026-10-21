"""Stop-preserving scheduled close coordination for target brackets."""

from __future__ import annotations

import math
from typing import NoReturn

from hypervector.live.hyperliquid_protocol import HyperliquidReconciliationSnapshot
from hypervector.live.asset_order_submission import AssetOrderSubmission
from hypervector.live.asset_partial_close import acknowledge_protected_partial_close
from hypervector.live.asset_bracket import (
    complete_bracket_visible,
    owned_exit_reason,
)
from hypervector.live.asset_consistency import (
    AssetReconciliationPoller,
    protected_order_visible,
)
from hypervector.live.asset_engine_contract import AssetLiveEngineError
from hypervector.live.asset_engine_events import AssetLiveEngineEvents
from hypervector.live.asset_state import (
    AssetLiveSnapshot,
    AssetLiveStateMachine,
)


def close_bracketed_position(
    *,
    snapshot: AssetLiveSnapshot,
    venue: HyperliquidReconciliationSnapshot,
    mark_price: float,
    reason: str,
    machine: AssetLiveStateMachine,
    events: AssetLiveEngineEvents,
    orders: AssetOrderSubmission,
    poller: AssetReconciliationPoller,
) -> AssetLiveSnapshot:
    """Cancel target first, close with stop armed, then clean residual stop."""
    stop_oid, target_oid, target_price = _required_bracket(snapshot)
    _require_owned_orders(venue, {stop_oid, target_oid}, events)
    events.emit_close_intent(reason=reason, stop_oid=stop_oid)
    machine.begin_exit()
    events.emit_state()
    cancel = orders.cancel_order(target_oid)
    events.emit_ack("cancel_target_for_close", cancel)
    prepared = poller.wait_for(
        lambda current: current.position.size_signed == 0.0 or not _has_order(current, target_oid)
    )
    if prepared.position.size_signed == 0.0:
        return _complete_intervening_exit(snapshot, prepared, machine, events, orders, poller)
    _require_stop_only(prepared, stop_oid, snapshot.position_size_signed, events)
    return _close_with_stop_armed(
        snapshot=snapshot,
        venue=prepared,
        mark_price=mark_price,
        reason=reason,
        stop_oid=stop_oid,
        target_price=target_price,
        machine=machine,
        events=events,
        orders=orders,
        poller=poller,
    )


def _close_with_stop_armed(
    *,
    snapshot: AssetLiveSnapshot,
    venue: HyperliquidReconciliationSnapshot,
    mark_price: float,
    reason: str,
    stop_oid: int,
    target_price: float,
    machine: AssetLiveStateMachine,
    events: AssetLiveEngineEvents,
    orders: AssetOrderSubmission,
    poller: AssetReconciliationPoller,
) -> AssetLiveSnapshot:
    close = orders.close_position(
        position_size_signed=venue.position.size_signed,
        mark_price=mark_price,
    )
    events.emit_ack("reduce_only_close", close, event_type="close")
    if not close.accepted or close.oid is None:
        return _recover_rejected_close(
            snapshot,
            machine,
            events,
            orders,
            poller,
            f"reduce-only close rejected: {close.error or close.status}",
        )
    machine.acknowledge_close(close.oid)
    after_close = poller.wait_for_close(machine.snapshot, close.oid)
    if after_close.position.size_signed != 0.0:
        if acknowledge_protected_partial_close(
            venue=after_close, close_oid=close.oid, machine=machine, events=events
        ):
            return restore_target_after_close_failure(
                snapshot=machine.snapshot,
                venue=after_close,
                target_price=target_price,
                machine=machine,
                events=events,
                orders=orders,
                poller=poller,
                failure="partial close",
            )
        _fault(events, "close acknowledged but protected exposure remains")
    return _finish_full_close(
        after_close, stop_oid, close.oid, reason, machine, events, orders, poller
    )


def _finish_full_close(
    after_close: HyperliquidReconciliationSnapshot,
    stop_oid: int,
    close_oid: int,
    reason: str,
    machine: AssetLiveStateMachine,
    events: AssetLiveEngineEvents,
    orders: AssetOrderSubmission,
    poller: AssetReconciliationPoller,
) -> AssetLiveSnapshot:
    _cancel_residual_orders(after_close, {stop_oid}, orders, events)
    after = poller.wait_for(lambda current: current.is_flat)
    if not after.is_flat:
        _fault(events, "post-close residual stop cleanup did not reconcile flat")
    machine.confirm_flat()
    events.emit_close_complete(reason=reason, oid=close_oid)
    events.emit_reconciliation(after)
    events.emit_state()
    return machine.snapshot


def _recover_rejected_close(
    snapshot: AssetLiveSnapshot,
    machine: AssetLiveStateMachine,
    events: AssetLiveEngineEvents,
    orders: AssetOrderSubmission,
    poller: AssetReconciliationPoller,
    failure: str,
) -> AssetLiveSnapshot:
    stop_oid, _, target_price = _required_bracket(snapshot)
    venue = poller.wait_for(
        lambda current: current.position.size_signed == 0.0
        or protected_order_visible(
            current,
            stop_oid=stop_oid,
            position_size_signed=snapshot.position_size_signed,
        )
    )
    if venue.position.size_signed == 0.0:
        return _complete_intervening_exit(snapshot, venue, machine, events, orders, poller)
    if not math.isclose(
        venue.position.size_signed,
        snapshot.position_size_signed,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        _fault(events, "rejected close changed position; execution evidence required")
    return restore_target_after_close_failure(
        snapshot=snapshot,
        venue=venue,
        target_price=target_price,
        machine=machine,
        events=events,
        orders=orders,
        poller=poller,
        failure=failure,
    )


def _complete_intervening_exit(
    snapshot: AssetLiveSnapshot,
    venue: HyperliquidReconciliationSnapshot,
    machine: AssetLiveStateMachine,
    events: AssetLiveEngineEvents,
    orders: AssetOrderSubmission,
    poller: AssetReconciliationPoller,
) -> AssetLiveSnapshot:
    stop_oid, target_oid, _ = _required_bracket(snapshot)
    exit_reason = owned_exit_reason(
        venue,
        stop_oid=stop_oid,
        target_oid=target_oid,
        position_size_signed=snapshot.position_size_signed,
        protective_progress=snapshot.protective_progress,
    )
    if exit_reason is None:
        _fault(events, "flat close preparation lacks exact owned bracket fill")
    _cancel_residual_orders(venue, {stop_oid, target_oid}, orders, events)
    after = poller.wait_for(lambda current: current.is_flat)
    if not after.is_flat:
        _fault(events, "intervening bracket fill cleanup did not reconcile flat")
    events.emit_reconciliation(after)
    events.confirm_owned_bracket_exit(
        reason=exit_reason,
        owned_oids=(stop_oid, target_oid),
    )
    return machine.snapshot


def restore_target_after_close_failure(
    *,
    snapshot: AssetLiveSnapshot,
    venue: HyperliquidReconciliationSnapshot,
    target_price: float,
    machine: AssetLiveStateMachine,
    events: AssetLiveEngineEvents,
    orders: AssetOrderSubmission,
    poller: AssetReconciliationPoller,
    failure: str,
) -> AssetLiveSnapshot:
    """Rebuild a required target while the original stop remains visible."""
    stop_oid = snapshot.stop_oid or 0
    _require_stop_only(venue, stop_oid, snapshot.position_size_signed, events)
    machine.begin_target_after_exit_failure(target_price=target_price)
    events.emit_state()
    ack = orders.place_target(
        position_size_signed=venue.position.size_signed,
        limit_price=target_price,
    )
    events.emit_ack("replacement_target", ack, event_type="target_order")
    if not ack.accepted or ack.oid is None:
        _fault(events, f"{failure}; replacement target failed")
    bracket = poller.wait_for(
        lambda current: complete_bracket_visible(
            current,
            stop_oid=stop_oid,
            target_oid=ack.oid,
            position_size_signed=snapshot.position_size_signed,
            target_price=target_price,
        )
    )
    if not complete_bracket_visible(
        bracket,
        stop_oid=stop_oid,
        target_oid=ack.oid,
        position_size_signed=snapshot.position_size_signed,
        target_price=target_price,
    ):
        _fault(events, f"{failure}; replacement bracket is not venue-visible")
    machine.confirm_target(target_oid=ack.oid)
    events.emit_reconciliation(bracket)
    events.emit_state()
    return machine.snapshot


def _required_bracket(snapshot: AssetLiveSnapshot) -> tuple[int, int, float]:
    if snapshot.stop_oid is None or snapshot.target_oid is None:
        raise AssetLiveEngineError("bracket close lacks owned order identity")
    if snapshot.target_price is None:
        raise AssetLiveEngineError("bracket close lacks target price")
    return snapshot.stop_oid, snapshot.target_oid, snapshot.target_price


def _require_stop_only(
    venue: HyperliquidReconciliationSnapshot,
    stop_oid: int,
    position_size_signed: float,
    events: AssetLiveEngineEvents,
) -> None:
    _require_owned_orders(venue, {stop_oid}, events)
    if not protected_order_visible(
        venue,
        stop_oid=stop_oid,
        position_size_signed=position_size_signed,
    ):
        _fault(events, "target cancellation removed or changed protective stop")


def _require_owned_orders(
    venue: HyperliquidReconciliationSnapshot,
    owned: set[int],
    events: AssetLiveEngineEvents,
) -> None:
    unknown = [order.oid for order in venue.open_orders if order.oid not in owned]
    if unknown:
        _fault(events, f"bracket close found unknown orders: {unknown}")


def _cancel_residual_orders(
    venue: HyperliquidReconciliationSnapshot,
    owned: set[int],
    orders: AssetOrderSubmission,
    events: AssetLiveEngineEvents,
) -> None:
    _require_owned_orders(venue, owned, events)
    for order in venue.open_orders:
        ack = orders.cancel_order(order.oid)
        events.emit_ack("cancel_residual_after_close", ack)
        if not ack.accepted:
            _fault(events, f"residual order cancel rejected: {ack.status}")


def _has_order(venue: HyperliquidReconciliationSnapshot, oid: int) -> bool:
    return any(order.oid == oid for order in venue.open_orders)


def _fault(events: AssetLiveEngineEvents, reason: str) -> NoReturn:
    events.fault(reason)
    raise AssetLiveEngineError(reason)
