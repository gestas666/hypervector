"""Fail-closed startup and committed-entry recovery for per-asset live execution."""

from __future__ import annotations

from hypervector.live.hyperliquid_protocol import (
    HyperliquidLiveAdapterProtocol,
    HyperliquidReconciliationSnapshot,
)
from hypervector.live.asset_cancel_restart import reconcile_cancel_fault
from hypervector.live.asset_cancel_restart_context import cancel_fault_context
from hypervector.live.asset_close_restart_context import (
    records_before_partial_close_fault,
)
from hypervector.live.asset_order_restart import (
    PendingAssetOrderIntent,
    AssetOrderRestartError,
    interrupted_lifecycle_intent,
    pending_order_intent,
    unresolved_order_intents,
)
from hypervector.live.asset_order_restart_context import (
    execution_plan_for_intent,
    latest_lifecycle_state,
    pending_entry_opened_at_ms,
    positive_number,
    required_text,
)
from hypervector.live.asset_order_submission import (
    AssetOrderSubmission,
)
from hypervector.live.asset_partial_protective_recovery import (
    AssetPartialProtectiveRecovery,
)
from hypervector.live.asset_partial_protective_restart_context import (
    records_before_partial_protective_fault,
)
from hypervector.live.asset_protective_cleanup_checkpoint import (
    pending_protective_cleanup,
)
from hypervector.live.asset_protective_execution_evidence import (
    ProtectiveExecutionEvidenceError,
)
from hypervector.live.asset_protective_journal import (
    validate_latest_protective_checkpoint,
)
from hypervector.live.asset_bracket_exit import (
    reconcile_owned_bracket_exit,
)
from hypervector.live.asset_engine_config import AssetEngineConfig
from hypervector.live.asset_consistency import AssetReconciliationPoller
from hypervector.live.asset_engine_events import AssetLiveEngineEvents
from hypervector.live.asset_exit_restart import (
    RecoveredPendingEntry,
    recover_pending_exit,
    resume_unprotected_position,
)
from hypervector.live.asset_ledger import AssetLiveLedger
from hypervector.live.asset_live_journal_orders import intent_for_oid
from hypervector.live.asset_live_telemetry import order_ack_payload
from hypervector.live.asset_reconcile import (
    RecoveredAssetOwnership,
    AssetStartupReconciliationError,
    reconcile_asset_startup,
)
from hypervector.live.asset_state import AssetLiveStateMachine
from hypervector.live.asset_stop_restart import recover_pending_stop
from hypervector.live.asset_target import EmergencyFlattenProtocol
from hypervector.live.asset_target_restart import recover_pending_target
from hypervector.live.hyperliquid_protocol import HyperliquidOrderAck
from hypervector.live.hyperliquid_parsing import HyperliquidOrderUnavailableError
from hypervector.live.asset_startup_support import _fault_and_raise, _recover_intent_ack
from hypervector.live.asset_startup_receipt_consistency import wait_for_stable_startup
from hypervector.live.asset_unresolved_intent_restart_context import (
    records_before_unresolved_intent_startup_fault,
)

UNINDEXED_RAISE_STATUS = "not_indexed_after_restart"
_RAISE_RECOVERY_OPERATION = "protective_stop_raise_restart_recovery"
_UNINDEXED_RAISE_ERROR = (
    "stop raise was never indexed by the venue; the original protective stop governs"
)


def prepare_asset_live_startup(
    *,
    config: AssetEngineConfig,
    adapter: HyperliquidLiveAdapterProtocol,
    ledger: AssetLiveLedger,
    machine: AssetLiveStateMachine,
    events: AssetLiveEngineEvents,
    orders: AssetOrderSubmission,
    poller: AssetReconciliationPoller,
    emergency_flatten: EmergencyFlattenProtocol,
    partial_protective: AssetPartialProtectiveRecovery | None = None,
) -> RecoveredPendingEntry | None:
    """Preflight venue state and return any filled entry needing protection."""
    prior_records, venue = _preflight_recovery(
        config, adapter, ledger, machine, events, orders, poller
    )
    cleaned, pending = _pending_after_cleanup(
        partial_protective, prior_records, venue, events, adapter, config
    )
    if cleaned:
        return None
    if _resume_partial_protection(
        partial_protective, prior_records, venue, pending, events
    ):
        return None
    if pending is not None:
        return _recover_pending_mutation(
            emergency_flatten=emergency_flatten,
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


def _resume_partial_protection(
    recovery: AssetPartialProtectiveRecovery | None,
    records: list[dict[str, object]],
    venue: HyperliquidReconciliationSnapshot,
    pending: PendingAssetOrderIntent | None,
    events: AssetLiveEngineEvents,
) -> bool:
    try:
        return recovery is not None and recovery.resume(records, venue, pending)
    except (
        AssetStartupReconciliationError,
        AssetOrderRestartError,
        ProtectiveExecutionEvidenceError,
    ) as exc:
        _fault_and_raise(events, exc)


def _preflight_recovery(
    config: AssetEngineConfig,
    adapter: HyperliquidLiveAdapterProtocol,
    ledger: AssetLiveLedger,
    machine: AssetLiveStateMachine,
    events: AssetLiveEngineEvents,
    orders: AssetOrderSubmission,
    poller: AssetReconciliationPoller,
) -> tuple[list[dict[str, object]], HyperliquidReconciliationSnapshot]:
    try:
        prior_records = _profile_recovery_records(ledger, config.profile_fingerprint)
        cancel_context = (
            None
            if pending_protective_cleanup(prior_records) is not None
            else cancel_fault_context(prior_records)
        )
    except AssetOrderRestartError as exc:
        _fault_and_raise(events, exc)
    machine.begin_preflight()
    events.emit("session_start", {"state": "PREFLIGHT"})
    events.emit_state()
    preflight = adapter.preflight(expected_max_leverage=int(config.venue_max_leverage))
    venue = adapter.reconcile()
    events.emit_preflight(preflight, venue)
    if cancel_context is not None:
        venue = reconcile_cancel_fault(cancel_context, orders, poller, events)
        prior_records = cancel_context.records
    return prior_records, venue


def _pending_intent(
    records: list[dict[str, object]],
    events: AssetLiveEngineEvents,
    adapter: HyperliquidLiveAdapterProtocol,
    config: AssetEngineConfig,
) -> PendingAssetOrderIntent | None:
    try:
        _resolve_unindexed_raise_intents(adapter, events, records, config)
        pending = pending_order_intent(records)
        if pending is None:
            pending = interrupted_lifecycle_intent(records)
        return pending
    except AssetOrderRestartError as exc:
        _fault_and_raise(events, exc)


def _resolve_unindexed_raise_intents(
    adapter: HyperliquidLiveAdapterProtocol,
    events: AssetLiveEngineEvents,
    records: list[dict[str, object]],
    config: AssetEngineConfig,
) -> None:
    """Durably retire several stop raises only when the venue indexed none of them.

    Any other unresolved operation, or any raise identity the venue does know,
    leaves the history untouched so the ambiguity still fails closed below.
    """
    pending = unresolved_order_intents(records)
    if len(pending) < 2 or any(
        intent.operation != "raise_protective_stop" for intent in pending
    ):
        return
    if any(_venue_indexed(adapter, intent) for intent in pending):
        return
    for intent in pending:
        _journal_unindexed_raise(events, records, intent, config)


def _venue_indexed(
    adapter: HyperliquidLiveAdapterProtocol, intent: PendingAssetOrderIntent
) -> bool:
    try:
        adapter.order_status_by_client_id(intent.client_order_id)
    except HyperliquidOrderUnavailableError:
        return False
    return True


def _journal_unindexed_raise(
    events: AssetLiveEngineEvents,
    records: list[dict[str, object]],
    intent: PendingAssetOrderIntent,
    config: AssetEngineConfig,
) -> None:
    """Persist that a raise never reached the venue, then mirror it in memory."""
    ack = HyperliquidOrderAck(
        accepted=False,
        oid=None,
        status=UNINDEXED_RAISE_STATUS,
        error=_UNINDEXED_RAISE_ERROR,
        client_order_id=intent.client_order_id,
        recovered_after_restart=True,
    )
    events.emit_ack(_RAISE_RECOVERY_OPERATION, ack, event_type="stop_order")
    records.append(
        {
            "event_type": "stop_order",
            "profile_fingerprint": config.profile_fingerprint,
            "payload": order_ack_payload(_RAISE_RECOVERY_OPERATION, ack),
        }
    )


def _pending_after_cleanup(
    recovery: AssetPartialProtectiveRecovery | None,
    records: list[dict[str, object]],
    venue: HyperliquidReconciliationSnapshot,
    events: AssetLiveEngineEvents,
    adapter: HyperliquidLiveAdapterProtocol,
    config: AssetEngineConfig,
) -> tuple[bool, PendingAssetOrderIntent | None]:
    try:
        if recovery is not None and recovery.resume_cleanup(records, venue):
            return True, None
    except (
        AssetStartupReconciliationError,
        AssetOrderRestartError,
        ProtectiveExecutionEvidenceError,
    ) as exc:
        _fault_and_raise(events, exc)
    return False, _pending_intent(records, events, adapter, config)


def _recover_pending_mutation(
    *,
    adapter: HyperliquidLiveAdapterProtocol,
    config: AssetEngineConfig,
    events: AssetLiveEngineEvents,
    machine: AssetLiveStateMachine,
    orders: AssetOrderSubmission,
    pending: PendingAssetOrderIntent,
    poller: AssetReconciliationPoller,
    records: list[dict[str, object]],
    venue: HyperliquidReconciliationSnapshot,
    emergency_flatten: EmergencyFlattenProtocol,
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
        return recover_pending_stop(
            poller=poller,
            emergency_flatten=emergency_flatten,
            config=config,
            events=events,
            machine=machine,
            orders=orders,
            pending=pending,
            records=records,
            venue=venue,
        )
    if pending.operation == "target":
        return _recover_target_mutation(
            adapter, events, machine, orders, pending, records, venue
        )
    if pending.operation == "raise_protective_stop":
        return _recover_pending_raise(
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


def _recover_pending_raise(
    *,
    adapter: HyperliquidLiveAdapterProtocol,
    config: AssetEngineConfig,
    events: AssetLiveEngineEvents,
    machine: AssetLiveStateMachine,
    orders: AssetOrderSubmission,
    pending: PendingAssetOrderIntent,
    poller: AssetReconciliationPoller,
    records: list[dict[str, object]],
    venue: HyperliquidReconciliationSnapshot,
) -> RecoveredPendingEntry | None:
    """Adopt a stop raised just before a crash, then resume the OPEN lifecycle exactly."""
    previous_oid = pending.payload.get("oid")
    try:
        status = adapter.order_status_by_client_id(pending.client_order_id)
    except HyperliquidOrderUnavailableError:
        # The venue never indexed the replacement identity: the original stop still
        # governs, and the normal OPEN recovery verifies it against the venue below.
        # Journal that outcome so the intent can never linger as unresolved.
        _journal_unindexed_raise(events, records, pending, config)
        status = None
    if status is not None:
        ack = HyperliquidOrderAck(
            accepted=status.status in {"open", "filled"},
            oid=status.oid,
            status=status.status,
            client_order_id=status.client_order_id,
        )
        events.emit_ack(
            "protective_stop_raise_restart_recovery", ack, event_type="stop_order"
        )
        if ack.accepted and ack.oid is not None and ack.oid != previous_oid:
            _adopt_raised_stop(records, previous_oid, ack.oid)
            events.emit(
                "protective_stop_raised",
                {
                    "previous_stop_oid": previous_oid,
                    "stop_oid": ack.oid,
                    "previous_trigger_price": None,
                    "trigger_price": pending.payload.get("trigger_price"),
                    "position_size_signed": pending.payload.get("position_size_signed"),
                    "recovered_after_restart": True,
                },
            )
    return _recover_latest_state(
        adapter=adapter,
        config=config,
        events=events,
        machine=machine,
        orders=orders,
        poller=poller,
        records=records,
        venue=venue,
    )


def _adopt_raised_stop(
    records: list[dict[str, object]], previous_oid: object, stop_oid: int
) -> None:
    for index in range(len(records) - 1, -1, -1):
        record = records[index]
        if record.get("event_type") != "state_transition":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict) or payload.get("state") != "OPEN":
            return
        if payload.get("stop_oid") != previous_oid:
            return
        records[index] = {**record, "payload": {**payload, "stop_oid": stop_oid}}
        return


def _recover_target_mutation(
    adapter: HyperliquidLiveAdapterProtocol,
    events: AssetLiveEngineEvents,
    machine: AssetLiveStateMachine,
    orders: AssetOrderSubmission,
    pending: PendingAssetOrderIntent,
    records: list[dict[str, object]],
    venue: HyperliquidReconciliationSnapshot,
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
    adapter: HyperliquidLiveAdapterProtocol,
    config: AssetEngineConfig,
    events: AssetLiveEngineEvents,
    machine: AssetLiveStateMachine,
    orders: AssetOrderSubmission,
    poller: AssetReconciliationPoller,
    records: list[dict[str, object]],
    venue: HyperliquidReconciliationSnapshot,
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
    events: AssetLiveEngineEvents,
) -> str | None:
    try:
        return latest_lifecycle_state(records)
    except AssetOrderRestartError as exc:
        _fault_and_raise(events, exc)


def _recover_pending_entry(
    *,
    adapter: HyperliquidLiveAdapterProtocol,
    config: AssetEngineConfig,
    events: AssetLiveEngineEvents,
    machine: AssetLiveStateMachine,
    orders: AssetOrderSubmission,
    pending: PendingAssetOrderIntent,
    records: list[dict[str, object]],
    venue: HyperliquidReconciliationSnapshot,
) -> RecoveredPendingEntry | None:
    try:
        side = required_text(pending.payload.get("side"), "pending entry side")
        mark_price = positive_number(
            pending.payload.get("mark_price"),
            "pending entry mark price",
        )
    except AssetOrderRestartError as exc:
        _fault_and_raise(events, exc)
    ack = _recover_intent_ack(events, orders, pending)
    events.emit_ack("entry_restart_recovery", ack)
    if not ack.accepted:
        _confirm_rejected_entry_is_flat(adapter, config, events, machine, venue)
        events.emit_state()
        return None
    if ack.oid is None or ack.venue_timestamp_ms is None:
        _fault_and_raise(
            events, AssetOrderRestartError("recovered entry identity incomplete")
        )
    if ack.status == "canceled":
        venue = adapter.reconcile()
    if venue.position.size_signed == 0.0:
        _fault_and_raise(
            events, AssetOrderRestartError("recovered entry has no exposure")
        )
    try:
        plan = execution_plan_for_intent(
            records, "ENTRY_PENDING", pending.client_order_id
        )
        opened_at_ms = pending_entry_opened_at_ms(pending, ack.venue_timestamp_ms)
    except AssetOrderRestartError as exc:
        _fault_and_raise(events, exc)
    machine.restore_pending_entry(entry_oid=ack.oid, execution_plan=plan)
    events.emit_state()
    return RecoveredPendingEntry(
        side=side,
        mark_price=mark_price,
        ack=ack,
        venue=venue,
        opened_at_ms=opened_at_ms,
    )


def _confirm_rejected_entry_is_flat(
    adapter: HyperliquidLiveAdapterProtocol,
    config: AssetEngineConfig,
    events: AssetLiveEngineEvents,
    machine: AssetLiveStateMachine,
    venue: HyperliquidReconciliationSnapshot,
) -> None:
    try:
        reconcile_asset_startup(
            records=[],
            venue=venue,
            expected_profile_fingerprint=config.profile_fingerprint,
        )
    except AssetStartupReconciliationError as exc:
        _fault_and_raise(events, exc)
    adapter.configure_isolated_leverage(int(config.leverage))
    machine.confirm_preflight_flat()


def _restore_stable_startup(
    *,
    adapter: HyperliquidLiveAdapterProtocol,
    config: AssetEngineConfig,
    events: AssetLiveEngineEvents,
    machine: AssetLiveStateMachine,
    orders: AssetOrderSubmission,
    poller: AssetReconciliationPoller,
    records: list[dict[str, object]],
    venue: HyperliquidReconciliationSnapshot,
) -> None:
    try:
        recovered, confirmed = wait_for_stable_startup(
            records=records,
            venue=venue,
            expected_profile_fingerprint=config.profile_fingerprint,
            poller=poller,
        )
    except AssetStartupReconciliationError as exc:
        _fault_and_raise(events, exc)
    if confirmed is not venue:
        events.emit_reconciliation(confirmed)
        venue = confirmed
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
        _fault_and_raise(events, AssetStartupReconciliationError("ownership missing"))
    adapter.configure_isolated_leverage(int(config.leverage))
    machine.confirm_preflight_flat()
    if ownership is not None:
        events.emit_recovered_stop_fill(stop_oid=ownership.stop_oid)


def _complete_stable_bracket_exit(
    *,
    adapter: HyperliquidLiveAdapterProtocol,
    config: AssetEngineConfig,
    events: AssetLiveEngineEvents,
    machine: AssetLiveStateMachine,
    orders: AssetOrderSubmission,
    ownership: RecoveredAssetOwnership,
    poller: AssetReconciliationPoller,
    venue: HyperliquidReconciliationSnapshot,
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
    machine: AssetLiveStateMachine,
    ownership: RecoveredAssetOwnership,
) -> None:
    machine.restore_protected_position(
        entry_oid=ownership.entry_oid,
        stop_oid=ownership.stop_oid,
        position_size_signed=ownership.position_size_signed,
        opened_at_ms=ownership.opened_at_ms,
        execution_plan=ownership.execution_plan,
        protective_progress=ownership.protective_progress,
        target_oid=ownership.target_oid,
        target_price=ownership.target_price,
    )


def _profile_recovery_records(
    ledger: AssetLiveLedger,
    expected_profile_fingerprint: str,
) -> list[dict[str, object]]:
    # Restart consumers read this profile's telemetry rows too, so the selection
    # is declared by profile only, never by event type.
    records = ledger.read_matching(
        lambda record: record.get("profile_fingerprint")
        == expected_profile_fingerprint,
        profile_fingerprint=expected_profile_fingerprint,
    )
    if pending_protective_cleanup(records) is None:
        records = records_before_partial_protective_fault(
            records_before_partial_close_fault(
                records_before_unresolved_intent_startup_fault(records)
            )
        )
    try:
        validate_latest_protective_checkpoint(records, intent_for_oid)
    except ValueError as exc:
        raise AssetOrderRestartError(
            f"protective checkpoint validation failed: {exc}"
        ) from exc
    return records
