"""Restart recovery for interrupted stop-only and bracketed exits."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import NoReturn

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolLiveAdapterProtocol,
    SolReconciliationSnapshot,
)
from hypervector.live.sol_order_restart import (
    PendingSolOrderIntent,
    SolOrderRestartError,
)
from hypervector.live.sol_order_restart_context import (
    PendingPositionContext,
    owned_open_record,
    pending_position_context,
    pending_position_context_for_intent,
)
from hypervector.live.sol_order_submission import (
    SolOrderRecoveryError,
    SolOrderSubmission,
    SolOrderSubmissionError,
)
from hypervector.live.sol_range_onset_bracket_close_restart import (
    recover_bracket_exit,
)
from hypervector.live.sol_partial_close import acknowledge_protected_partial_close
from hypervector.live.sol_close_restart_context import PARTIAL_CLOSE_UNRESOLVED
from hypervector.live.sol_range_onset_config import SolRangeOnsetConfig
from hypervector.live.sol_range_onset_consistency import SolReconciliationPoller
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_reconcile import (
    SolStartupReconciliationError,
    reconcile_sol_startup,
)
from hypervector.live.sol_range_onset_state import SolLiveStateMachine
from hypervector.live.sol_range_onset_stop_close import (
    cancel_residual_stop_after_close,
)


@dataclass(frozen=True)
class RecoveredPendingEntry:
    """Venue-verified entry context that still requires native protection."""

    side: str
    mark_price: float
    ack: HyperliquidOrderAck
    venue: SolReconciliationSnapshot
    opened_at_ms: int


def recover_pending_exit(
    *,
    adapter: SolLiveAdapterProtocol,
    config: SolRangeOnsetConfig,
    events: SolLiveEngineEvents,
    machine: SolLiveStateMachine,
    orders: SolOrderSubmission,
    pending: PendingSolOrderIntent | None,
    poller: SolReconciliationPoller,
    records: list[dict[str, object]],
    venue: SolReconciliationSnapshot,
) -> RecoveredPendingEntry | None:
    """Recover an exact interrupted exit or return exposure for reprotection."""
    context = _exit_context(events, records, pending)
    if context.target_oid is not None:
        disposition = recover_bracket_exit(
            context=context,
            events=events,
            machine=machine,
            orders=orders,
            pending=pending,
            poller=poller,
            venue=venue,
        )
        if disposition == "resume_unprotected":
            return resume_unprotected_position(
                events=events,
                machine=machine,
                records=records,
                expected_state="EXIT_PENDING",
                venue=venue,
                allow_reduced_size=pending is not None,
                context=context,
            )
        return None
    if pending is None:
        return _recover_exit_without_close(adapter, config, events, machine, records, venue)
    return _recover_pending_close(
        adapter, config, events, machine, orders, pending, poller, records, venue
    )


def resume_unprotected_position(
    *,
    events: SolLiveEngineEvents,
    machine: SolLiveStateMachine,
    records: list[dict[str, object]],
    expected_state: str,
    venue: SolReconciliationSnapshot,
    allow_reduced_size: bool = False,
    context: PendingPositionContext | None = None,
) -> RecoveredPendingEntry:
    """Adopt exact unprotected exposure so the engine immediately protects it."""
    try:
        if context is None:
            context = pending_position_context(records, expected_state)
    except SolOrderRestartError as exc:
        _fault(events, exc)
    observed_size = venue.position.size_signed
    if venue.open_orders or not _size_matches(
        expected=context.position_size_signed,
        observed=observed_size,
        allow_reduced=allow_reduced_size,
    ):
        _fault(events, SolOrderRestartError("unprotected exposure mismatches ledger"))
    entry_price = venue.position.entry_price
    if entry_price is None or entry_price <= 0.0:
        _fault(events, SolOrderRestartError("entry price is unavailable"))
    machine.restore_pending_entry(
        entry_oid=context.entry_oid,
        execution_plan=context.execution_plan,
        protective_progress=context.protective_progress,
    )
    events.emit_state()
    return _recovered_entry(
        context.entry_oid,
        observed_size,
        entry_price,
        context,
        venue,
    )


def _recover_exit_without_close(
    adapter: SolLiveAdapterProtocol,
    config: SolRangeOnsetConfig,
    events: SolLiveEngineEvents,
    machine: SolLiveStateMachine,
    records: list[dict[str, object]],
    venue: SolReconciliationSnapshot,
    context: PendingPositionContext | None = None,
) -> RecoveredPendingEntry | None:
    if context is None:
        context = _exit_context(events, records)
    if context.stop_oid is None:
        _fault(events, SolOrderRestartError("pending exit lacks stop oid"))
    if venue.position.size_signed != 0.0 and not venue.open_orders:
        return resume_unprotected_position(
            events=events,
            machine=machine,
            records=records,
            expected_state="EXIT_PENDING",
            venue=venue,
            context=context,
        )
    try:
        record = owned_open_record(
            context,
            context.stop_oid,
            config.profile_fingerprint,
        )
        recovered = reconcile_sol_startup(
            records=[record],
            venue=venue,
            expected_profile_fingerprint=config.profile_fingerprint,
        )
    except SolStartupReconciliationError as exc:
        _fault(events, exc)
    if recovered.disposition == "restore_open":
        _restore_open(machine, context)
        events.emit_reconciliation(venue)
        events.emit_state()
        return None
    adapter.configure_isolated_leverage(int(config.leverage))
    machine.confirm_preflight_flat()
    events.emit_recovered_stop_fill(stop_oid=context.stop_oid)
    events.emit_reconciliation(venue)
    events.emit_state()
    return None


def _recover_pending_close(
    adapter: SolLiveAdapterProtocol,
    config: SolRangeOnsetConfig,
    events: SolLiveEngineEvents,
    machine: SolLiveStateMachine,
    orders: SolOrderSubmission,
    pending: PendingSolOrderIntent,
    poller: SolReconciliationPoller,
    records: list[dict[str, object]],
    venue: SolReconciliationSnapshot,
) -> RecoveredPendingEntry | None:
    context = _exit_context(events, records, pending)
    if context.stop_oid is None:
        _fault(events, SolOrderRestartError("pending close lacks stop oid"))
    ack = _recover_ack(events, orders, pending)
    events.emit_ack("reduce_only_close_restart_recovery", ack, event_type="close")
    if not ack.accepted and ack.status in {"canceled", "rejected"}:
        return _recover_exit_without_close(
            adapter, config, events, machine, records, venue, context
        )
    if not ack.accepted or ack.oid is None or ack.status not in {"filled", "canceled"}:
        _fault(events, SolOrderRestartError("recovered close is unresolved"))
    if venue.position.size_signed != 0.0 and not venue.open_orders:
        return resume_unprotected_position(
            events=events,
            machine=machine,
            records=records,
            expected_state="EXIT_PENDING",
            venue=venue,
            allow_reduced_size=True,
            context=context,
        )
    _complete_pending_close(
        context=context,
        close_oid=ack.oid,
        venue=venue,
        machine=machine,
        events=events,
        orders=orders,
        poller=poller,
    )
    return None


def _complete_pending_close(
    *,
    context: PendingPositionContext,
    close_oid: int,
    venue: SolReconciliationSnapshot,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
) -> None:
    machine.restore_exit_pending(
        entry_oid=context.entry_oid,
        stop_oid=context.stop_oid,
        position_size_signed=context.position_size_signed,
        opened_at_ms=context.opened_at_ms,
        execution_plan=context.execution_plan,
        protective_progress=context.protective_progress,
    )
    events.emit_state()
    machine.acknowledge_close(close_oid)
    if venue.position.size_signed != 0.0:
        venue = poller.wait_for_close(machine.snapshot, close_oid)
    if acknowledge_protected_partial_close(
        venue=venue, close_oid=close_oid, machine=machine, events=events
    ):
        machine.restore_protection_after_exit_failure(stop_oid=context.stop_oid or 0)
        events.emit_state()
        return
    if venue.position.size_signed != 0.0:
        _fault(events, SolOrderRestartError(PARTIAL_CLOSE_UNRESOLVED))
    after = cancel_residual_stop_after_close(
        venue=venue,
        stop_oid=context.stop_oid,
        events=events,
        orders=orders,
        poller=poller,
    )
    if not after.is_flat:
        _fault(events, SolOrderRestartError("recovered close is not flat"))
    machine.confirm_flat()
    events.emit_close_complete(reason="restart_recovery", oid=close_oid)
    events.emit_reconciliation(after)
    events.emit_state()


def _recover_ack(
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    pending: PendingSolOrderIntent,
) -> HyperliquidOrderAck:
    try:
        return orders.recover_existing_intent(
            operation=pending.operation,
            client_order_id=pending.client_order_id,
        )
    except SolOrderRecoveryError as exc:
        raise SolLiveEngineError(str(exc)) from exc
    except SolOrderSubmissionError as exc:
        _fault(events, exc)


def _restore_open(
    machine: SolLiveStateMachine,
    context: PendingPositionContext,
) -> None:
    if context.stop_oid is None:
        raise SolLiveEngineError("protected restart context lacks stop ownership")
    machine.restore_protected_position(
        entry_oid=context.entry_oid,
        stop_oid=context.stop_oid,
        position_size_signed=context.position_size_signed,
        opened_at_ms=context.opened_at_ms,
        execution_plan=context.execution_plan,
        protective_progress=context.protective_progress,
    )


def _recovered_entry(
    entry_oid: int,
    observed_size: float,
    entry_price: float,
    context: PendingPositionContext,
    venue: SolReconciliationSnapshot,
) -> RecoveredPendingEntry:
    ack = HyperliquidOrderAck(
        accepted=True,
        oid=entry_oid,
        status="restart_reconciled",
        filled_size=abs(observed_size),
        average_price=entry_price,
        recovered_after_restart=True,
        venue_timestamp_ms=context.opened_at_ms,
    )
    return RecoveredPendingEntry(
        side="long" if observed_size > 0.0 else "short",
        mark_price=entry_price,
        ack=ack,
        venue=venue,
        opened_at_ms=context.opened_at_ms,
    )


def _exit_context(
    events: SolLiveEngineEvents,
    records: list[dict[str, object]],
    pending: PendingSolOrderIntent | None = None,
) -> PendingPositionContext:
    try:
        if pending is not None:
            return pending_position_context_for_intent(
                records, "EXIT_PENDING", pending.client_order_id
            )
        return pending_position_context(records, "EXIT_PENDING")
    except SolOrderRestartError as exc:
        _fault(events, exc)


def _size_matches(*, expected: float, observed: float, allow_reduced: bool) -> bool:
    if observed == 0.0 or (observed > 0.0) != (expected > 0.0):
        return False
    if math.isclose(observed, expected, rel_tol=0.0, abs_tol=1e-9):
        return True
    return allow_reduced and abs(observed) < abs(expected)


def _fault(events: SolLiveEngineEvents, error: Exception) -> NoReturn:
    reason = str(error)
    events.fault(reason)
    raise SolLiveEngineError(reason) from error
