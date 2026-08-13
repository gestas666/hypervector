"""Fail-closed startup and committed-entry recovery for SOL live execution."""

from __future__ import annotations

from typing import NoReturn

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolLiveAdapterProtocol,
    SolReconciliationSnapshot,
)
from hypervector.live.sol_order_restart import (
    PendingSolOrderIntent,
    SolOrderRestartError,
    interrupted_lifecycle_intent,
    pending_order_intent,
)
from hypervector.live.sol_order_restart_context import (
    PendingPositionContext,
    execution_plan_for_state,
    latest_lifecycle_state,
    owned_open_record,
    pending_position_context,
    positive_number,
    required_text,
)
from hypervector.live.sol_order_submission import (
    SolOrderRecoveryError,
    SolOrderSubmission,
    SolOrderSubmissionError,
)
from hypervector.live.sol_range_onset_consistency import SolReconciliationPoller
from hypervector.live.sol_range_onset_config import SolRangeOnsetConfig
from hypervector.live.sol_range_onset_bracket_exit import (
    reconcile_owned_bracket_exit,
)
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_exit_restart import (
    RecoveredPendingEntry,
    recover_pending_exit,
    resume_unprotected_position,
)
from hypervector.live.sol_range_onset_ledger import SolLiveLedger
from hypervector.live.sol_range_onset_reconcile import (
    RecoveredSolOwnership,
    SolStartupReconciliationError,
    reconcile_sol_startup,
)
from hypervector.live.sol_range_onset_state import SolLiveStateMachine
from hypervector.live.sol_range_onset_target_restart import recover_pending_target


def prepare_sol_live_startup(
    *,
    config: SolRangeOnsetConfig,
    adapter: SolLiveAdapterProtocol,
    ledger: SolLiveLedger,
    machine: SolLiveStateMachine,
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
) -> RecoveredPendingEntry | None:
    """Preflight venue state and return any filled entry needing protection."""
    prior_records = _profile_records(ledger.read_all(), config.profile_fingerprint)
    machine.begin_preflight()
    events.emit("session_start", {"state": "PREFLIGHT"})
    events.emit_state()
    preflight = adapter.preflight(expected_max_leverage=int(config.venue_max_leverage))
    venue = adapter.reconcile()
    events.emit_preflight(preflight, venue)
    pending = _pending_intent(prior_records, events)
    if pending is not None:
        return _recover_pending_mutation(
            adapter=adapter,
            config=config,
            events=events,
            machine=machine,
            orders=orders,
            pending=pending,
            poller=poller,
            records=prior_records,
            venue=venue,
        )
    return _recover_latest_state(
        adapter=adapter,
        config=config,
        events=events,
        machine=machine,
        orders=orders,
        poller=poller,
        records=prior_records,
        venue=venue,
    )


def _pending_intent(
    records: list[dict[str, object]],
    events: SolLiveEngineEvents,
) -> PendingSolOrderIntent | None:
    try:
        pending = pending_order_intent(records)
        if pending is None:
            pending = interrupted_lifecycle_intent(records)
        return pending
    except SolOrderRestartError as exc:
        _fault_and_raise(events, exc)


def _recover_pending_mutation(
    *,
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
    if pending.operation == "entry":
        return _recover_pending_entry(
            adapter=adapter,
            config=config,
            events=events,
            machine=machine,
            orders=orders,
            pending=pending,
            records=records,
            venue=venue,
        )
    if pending.operation == "protective_stop":
        return _recover_pending_stop(
            config=config,
            events=events,
            machine=machine,
            orders=orders,
            pending=pending,
            records=records,
            venue=venue,
        )
    if pending.operation == "target":
        _recover_target_mutation(
            adapter, events, machine, orders, pending, records, venue
        )
        return None
    return recover_pending_exit(
        adapter=adapter,
        config=config,
        events=events,
        machine=machine,
        orders=orders,
        pending=pending,
        poller=poller,
        records=records,
        venue=venue,
    )


def _recover_target_mutation(
    adapter: SolLiveAdapterProtocol,
    events: SolLiveEngineEvents,
    machine: SolLiveStateMachine,
    orders: SolOrderSubmission,
    pending: PendingSolOrderIntent,
    records: list[dict[str, object]],
    venue: SolReconciliationSnapshot,
) -> None:
    recover_pending_target(
        adapter=adapter,
        events=events,
        machine=machine,
        orders=orders,
        pending=pending,
        records=records,
        venue=venue,
    )


def _recover_latest_state(
    *,
    adapter: SolLiveAdapterProtocol,
    config: SolRangeOnsetConfig,
    events: SolLiveEngineEvents,
    machine: SolLiveStateMachine,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
    records: list[dict[str, object]],
    venue: SolReconciliationSnapshot,
) -> RecoveredPendingEntry | None:
    lifecycle_state = _latest_state(records, events)

    if lifecycle_state == "ENTRY_PENDING":
        _confirm_rejected_entry_is_flat(adapter, config, events, machine, venue)
        events.emit_state()
        return None
    if lifecycle_state == "PROTECTING":
        return resume_unprotected_position(
            events=events,
            machine=machine,
            records=records,
            expected_state="PROTECTING",
            venue=venue,
        )
    if lifecycle_state == "EXIT_PENDING":
        return recover_pending_exit(
            adapter=adapter,
            config=config,
            events=events,
            machine=machine,
            orders=orders,
            pending=None,
            poller=poller,
            records=records,
            venue=venue,
        )
    _restore_stable_startup(
        adapter=adapter,
        config=config,
        events=events,
        machine=machine,
        orders=orders,
        poller=poller,
        records=records,
        venue=venue,
    )
    events.emit_state()
    return None


def _latest_state(
    records: list[dict[str, object]],
    events: SolLiveEngineEvents,
) -> str | None:
    try:
        return latest_lifecycle_state(records)
    except SolOrderRestartError as exc:
        _fault_and_raise(events, exc)


def _recover_pending_entry(
    *,
    adapter: SolLiveAdapterProtocol,
    config: SolRangeOnsetConfig,
    events: SolLiveEngineEvents,
    machine: SolLiveStateMachine,
    orders: SolOrderSubmission,
    pending: PendingSolOrderIntent,
    records: list[dict[str, object]],
    venue: SolReconciliationSnapshot,
) -> RecoveredPendingEntry | None:
    try:
        side = required_text(pending.payload.get("side"), "pending entry side")
        mark_price = positive_number(
            pending.payload.get("mark_price"),
            "pending entry mark price",
        )
    except SolOrderRestartError as exc:
        _fault_and_raise(events, exc)
    ack = _recover_intent_ack(events, orders, pending)
    events.emit_ack("entry_restart_recovery", ack)
    if not ack.accepted:
        _confirm_rejected_entry_is_flat(adapter, config, events, machine, venue)
        events.emit_state()
        return None
    if ack.oid is None or ack.venue_timestamp_ms is None:
        _fault_and_raise(
            events, SolOrderRestartError("recovered entry identity incomplete")
        )
    if venue.position.size_signed == 0.0:
        _fault_and_raise(
            events, SolOrderRestartError("recovered entry has no exposure")
        )
    try:
        plan = execution_plan_for_state(records, "ENTRY_PENDING")
    except SolOrderRestartError as exc:
        _fault_and_raise(events, exc)
    machine.restore_pending_entry(entry_oid=ack.oid, execution_plan=plan)
    events.emit_state()
    return RecoveredPendingEntry(
        side=side,
        mark_price=mark_price,
        ack=ack,
        venue=venue,
        opened_at_ms=ack.venue_timestamp_ms,
    )


def _recover_pending_stop(
    *,
    config: SolRangeOnsetConfig,
    events: SolLiveEngineEvents,
    machine: SolLiveStateMachine,
    orders: SolOrderSubmission,
    pending: PendingSolOrderIntent,
    records: list[dict[str, object]],
    venue: SolReconciliationSnapshot,
) -> RecoveredPendingEntry | None:
    try:
        context = pending_position_context(records, "PROTECTING")
    except SolOrderRestartError as exc:
        _fault_and_raise(events, exc)
    ack = _recover_intent_ack(events, orders, pending)
    events.emit_ack("protective_stop_restart_recovery", ack, event_type="stop_order")
    if ack.status in {"canceled", "rejected"}:
        return resume_unprotected_position(
            events=events,
            machine=machine,
            records=records,
            expected_state="PROTECTING",
            venue=venue,
        )
    if not ack.accepted or ack.oid is None:
        _fault_and_raise(events, SolOrderRestartError("recovered stop is unresolved"))
    if ack.status == "filled" and venue.position.size_signed != 0.0:
        return resume_unprotected_position(
            events=events,
            machine=machine,
            records=records,
            expected_state="PROTECTING",
            venue=venue,
            allow_reduced_size=True,
        )
    return _finalize_recovered_stop(
        context=context,
        ack=ack,
        events=events,
        machine=machine,
        venue=venue,
        expected_profile_fingerprint=config.profile_fingerprint,
    )


def _finalize_recovered_stop(
    *,
    context: PendingPositionContext,
    ack: HyperliquidOrderAck,
    events: SolLiveEngineEvents,
    machine: SolLiveStateMachine,
    venue: SolReconciliationSnapshot,
    expected_profile_fingerprint: str,
) -> None:
    if ack.oid is None:
        _fault_and_raise(events, SolOrderRestartError("recovered stop lacks oid"))
    machine.restore_protecting_position(
        entry_oid=context.entry_oid,
        position_size_signed=context.position_size_signed,
        opened_at_ms=context.opened_at_ms,
        execution_plan=context.execution_plan,
    )
    events.emit_state()
    record = owned_open_record(context, ack.oid, expected_profile_fingerprint)
    try:
        recovered = reconcile_sol_startup(
            records=[record],
            venue=venue,
            expected_profile_fingerprint=expected_profile_fingerprint,
        )
    except SolStartupReconciliationError as exc:
        _fault_and_raise(events, exc)
    events.emit_reconciliation(venue)
    if recovered.disposition == "protective_stop_filled":
        events.confirm_stop_fill_during_protection(stop_oid=ack.oid)
        return None
    machine.confirm_protection(stop_oid=ack.oid)
    events.emit_state()
    return None


def _recover_intent_ack(
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
        _fault_and_raise(events, exc)


def _confirm_rejected_entry_is_flat(
    adapter: SolLiveAdapterProtocol,
    config: SolRangeOnsetConfig,
    events: SolLiveEngineEvents,
    machine: SolLiveStateMachine,
    venue: SolReconciliationSnapshot,
) -> None:
    try:
        reconcile_sol_startup(
            records=[],
            venue=venue,
            expected_profile_fingerprint=config.profile_fingerprint,
        )
    except SolStartupReconciliationError as exc:
        _fault_and_raise(events, exc)
    adapter.configure_isolated_leverage(int(config.leverage))
    machine.confirm_preflight_flat()


def _restore_stable_startup(
    *,
    adapter: SolLiveAdapterProtocol,
    config: SolRangeOnsetConfig,
    events: SolLiveEngineEvents,
    machine: SolLiveStateMachine,
    orders: SolOrderSubmission,
    poller: SolReconciliationPoller,
    records: list[dict[str, object]],
    venue: SolReconciliationSnapshot,
) -> None:
    try:
        recovered = reconcile_sol_startup(
            records=records,
            venue=venue,
            expected_profile_fingerprint=config.profile_fingerprint,
        )
    except SolStartupReconciliationError as exc:
        _fault_and_raise(events, exc)
    ownership = recovered.ownership
    if recovered.disposition == "owned_bracket_filled" and ownership is not None:
        _complete_stable_bracket_exit(
            adapter=adapter,
            config=config,
            events=events,
            machine=machine,
            orders=orders,
            ownership=ownership,
            poller=poller,
            venue=venue,
        )
        return
    if recovered.disposition == "restore_open" and ownership is not None:
        _restore_owned_position(machine, ownership)
        return
    if recovered.disposition == "restore_open":
        _fault_and_raise(events, SolStartupReconciliationError("ownership missing"))
    adapter.configure_isolated_leverage(int(config.leverage))
    machine.confirm_preflight_flat()
    if ownership is not None:
        events.emit_recovered_stop_fill(stop_oid=ownership.stop_oid)


def _complete_stable_bracket_exit(
    *,
    adapter: SolLiveAdapterProtocol,
    config: SolRangeOnsetConfig,
    events: SolLiveEngineEvents,
    machine: SolLiveStateMachine,
    orders: SolOrderSubmission,
    ownership: RecoveredSolOwnership,
    poller: SolReconciliationPoller,
    venue: SolReconciliationSnapshot,
) -> None:
    _restore_owned_position(machine, ownership)
    reconcile_owned_bracket_exit(
        snapshot=machine.snapshot,
        venue=venue,
        orders=orders,
        events=events,
        poller=poller,
    )
    adapter.configure_isolated_leverage(int(config.leverage))


def _restore_owned_position(
    machine: SolLiveStateMachine,
    ownership: RecoveredSolOwnership,
) -> None:
    machine.restore_protected_position(
        entry_oid=ownership.entry_oid,
        stop_oid=ownership.stop_oid,
        position_size_signed=ownership.position_size_signed,
        opened_at_ms=ownership.opened_at_ms,
        execution_plan=ownership.execution_plan,
        target_oid=ownership.target_oid,
        target_price=ownership.target_price,
    )


def _fault_and_raise(events: SolLiveEngineEvents, error: Exception) -> NoReturn:
    reason = str(error)
    events.fault(reason)
    raise SolLiveEngineError(reason) from error


def _profile_records(
    records: list[dict[str, object]],
    expected_profile_fingerprint: str,
) -> list[dict[str, object]]:
    return [
        record
        for record in records
        if record.get("profile_fingerprint") == expected_profile_fingerprint
    ]
