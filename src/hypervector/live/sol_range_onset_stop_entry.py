"""Protect a reconciled entry before it can become OPEN."""

from __future__ import annotations

from typing import NoReturn, Protocol

from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.sol_order_submission import SolOrderSubmission
from hypervector.live.sol_range_onset_config import SolRangeOnsetConfig
from hypervector.live.sol_range_onset_consistency import (
    SolReconciliationPoller,
    protected_order_visible,
)
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_execution_plan import legacy_execution_plan
from hypervector.live.sol_range_onset_reconcile import (
    SolStartupReconciliationError,
)
from hypervector.live.sol_range_onset_state import (
    SolLiveSnapshot,
    SolLiveStateMachine,
)
from hypervector.live.sol_range_onset_target import complete_entry_protection
from hypervector.live.sol_range_onset_verification import verify_protected_position


class EmergencyFlatten(Protocol):
    """Callable boundary for fail-closed protection failures."""

    def __call__(
        self,
        *,
        position_size_signed: float,
        mark_price: float,
        reason: str,
        stop_oid: int | None = None,
    ) -> NoReturn:
        """Flatten unresolved exposure or raise after a persisted fault."""
        ...


def place_and_verify_entry_protection(
    *,
    config: SolRangeOnsetConfig,
    entry_oid: int,
    position_size_signed: float,
    trigger_price: float,
    mark_price: float,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
    emergency_flatten: EmergencyFlatten,
) -> SolLiveSnapshot:
    """Place the exact stop, reconcile it, then add an optional target."""
    stop_ack = orders.place_protective_stop(
        position_size_signed=position_size_signed,
        trigger_price=trigger_price,
    )
    events.emit_ack("protective_stop", stop_ack, event_type="stop_order")
    if not stop_ack.accepted or stop_ack.oid is None:
        emergency_flatten(
            position_size_signed=position_size_signed,
            mark_price=mark_price,
            reason=f"protective stop rejected: {stop_ack.error or stop_ack.status}",
        )
    protected = poller.wait_for(
        lambda venue: protected_order_visible(
            venue,
            stop_oid=stop_ack.oid,
            position_size_signed=position_size_signed,
        )
    )
    return _complete_verified_protection(
        config=config,
        entry_oid=entry_oid,
        position_size_signed=position_size_signed,
        stop_oid=stop_ack.oid,
        mark_price=mark_price,
        machine=machine,
        events=events,
        orders=orders,
        poller=poller,
        emergency_flatten=emergency_flatten,
        protected=protected,
    )


def _complete_verified_protection(
    *,
    config: SolRangeOnsetConfig,
    entry_oid: int,
    position_size_signed: float,
    stop_oid: int,
    mark_price: float,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
    emergency_flatten: EmergencyFlatten,
    protected: SolReconciliationSnapshot,
) -> SolLiveSnapshot:
    try:
        stop_filled = verify_protected_position(
            entry_oid=entry_oid,
            stop_oid=stop_oid,
            position_size_signed=position_size_signed,
            opened_at_ms=machine.snapshot.opened_at_ms,
            venue=protected,
        )
    except SolStartupReconciliationError as exc:
        emergency_flatten(
            position_size_signed=protected.position.size_signed,
            mark_price=mark_price,
            reason=f"protective stop reconciliation failed: {exc}",
            stop_oid=stop_oid,
        )
    if stop_filled:
        events.emit_reconciliation(protected)
        events.confirm_stop_fill_during_protection(stop_oid=stop_oid)
        return machine.snapshot
    events.emit_reconciliation(protected)
    return _complete_optional_target(
        config=config,
        position_size_signed=position_size_signed,
        stop_oid=stop_oid,
        mark_price=mark_price,
        machine=machine,
        events=events,
        orders=orders,
        poller=poller,
        emergency_flatten=emergency_flatten,
        protected=protected,
    )


def _complete_optional_target(
    *,
    config: SolRangeOnsetConfig,
    position_size_signed: float,
    stop_oid: int,
    mark_price: float,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
    emergency_flatten: EmergencyFlatten,
    protected: SolReconciliationSnapshot,
) -> SolLiveSnapshot:
    plan = machine.snapshot.execution_plan or legacy_execution_plan(config)
    entry_price = protected.position.entry_price
    if entry_price is None:
        emergency_flatten(
            position_size_signed=position_size_signed,
            mark_price=mark_price,
            reason="entry price unavailable before target placement",
            stop_oid=stop_oid,
        )
    return complete_entry_protection(
        plan=plan,
        entry_price=entry_price,
        position_size_signed=position_size_signed,
        stop_oid=stop_oid,
        mark_price=mark_price,
        machine=machine,
        events=events,
        orders=orders,
        poller=poller,
        emergency_flatten=emergency_flatten,
    )
