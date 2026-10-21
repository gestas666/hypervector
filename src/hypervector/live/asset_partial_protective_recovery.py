"""Receipt-backed partial target adoption and completion of an owned stop exit."""

import math
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidReconciliationSnapshot,
)
from hypervector.live.asset_order_restart import PendingAssetOrderIntent
from hypervector.live.asset_order_restart_context import (
    PendingPositionContext,
    latest_lifecycle_state,
    pending_position_context,
    pending_position_context_for_intent,
)
from hypervector.live.asset_order_submission import AssetOrderSubmission
from hypervector.live.asset_protective_checkpoint import PARTIAL_PROTECTIVE_UNRESOLVED
from hypervector.live.asset_protective_cleanup_actions import finish_protective_cleanup
from hypervector.live.asset_protective_cleanup_checkpoint import (
    cleanup_checkpoint_payload,
    pending_protective_cleanup,
)
from hypervector.live.asset_protective_cleanup_suffix import validate_cleanup_suffix
from hypervector.live.asset_protective_execution_evidence import (
    ProtectiveExecutionEvidenceError,
    ProtectiveExecutionProgress,
    observe_protective_execution,
)
from hypervector.live.asset_consistency import AssetReconciliationPoller
from hypervector.live.asset_engine_events import AssetLiveEngineEvents
from hypervector.live.asset_reconcile import AssetStartupReconciliationError
from hypervector.live.asset_state import (
    AssetLiveSnapshot,
    AssetLiveState,
    AssetLiveStateMachine,
)
from hypervector.live.asset_verification import verify_open_snapshot


class AssetPartialProtectiveRecovery:
    """Keep receipt credit and stop-exit intent effective through bounded reconciliation."""

    def __init__(
        self,
        *,
        machine: AssetLiveStateMachine,
        events: AssetLiveEngineEvents,
        orders: AssetOrderSubmission,
        poller: AssetReconciliationPoller,
        now_fn: Callable[[], datetime],
    ) -> None:
        """Reuse the engine's exact mutation, ledger, clock and venue-read boundaries."""
        self._machine, self._events = machine, events
        self._orders, self._poller, self._now_fn = orders, poller, now_fn

    def reconcile(self, venue: HyperliquidReconciliationSnapshot) -> HyperliquidReconciliationSnapshot | None:
        """Adopt only attributed protected targets, or continue a recorded partial stop exit."""
        before = self._machine.snapshot
        if (
            before.state is AssetLiveState.EXIT_PENDING
            and before.protective_progress.stop_exit_required
        ):
            return self._close_remainder(venue, None)
        if before.state is not AssetLiveState.OPEN or venue.position.size_signed == 0:
            return None
        if (
            venue.position.size_signed == before.position_size_signed
            and not before.protective_progress.fills
        ):
            return None
        progress = self._observe(before, venue)
        self._require_remaining_orders(before, venue, progress)
        if progress == before.protective_progress:
            return None
        self._checkpoint(venue, progress)
        return self._close_remainder(venue, None) if progress.stop_exit_required else venue

    def resume(
        self,
        records: list[dict[str, object]],
        venue: HyperliquidReconciliationSnapshot,
        pending: PendingAssetOrderIntent | None,
    ) -> bool:
        """Recover a partial protective observation or an already-recorded stop obligation."""
        state = latest_lifecycle_state(records)
        if state not in {"OPEN", "STOPPED", "EXIT_PENDING"}:
            return False
        latest = next(
            row["payload"]
            for row in reversed(records)
            if row.get("event_type") == "state_transition"
        )
        if latest.get("position_size_signed", 0) == 0:
            return False
        context = (
            pending_position_context_for_intent(records, "EXIT_PENDING", pending.client_order_id)
            if pending is not None and state == "EXIT_PENDING"
            else pending_position_context(records, state)
        )
        if not self._applies_to_restart(state, context, venue):
            return False
        if pending is not None and (
            pending.operation != "reduce_only_close"
            or not context.protective_progress.stop_exit_required
        ):
            raise AssetStartupReconciliationError(
                "partial protection conflicts with a pending mutation"
            )
        if context.protective_progress.stop_exit_required:
            self._restore(context, context.position_size_signed, context.protective_progress)
            self._close_remainder(venue, pending)
            return True
        before = _context_snapshot(context)
        progress = self._observe(before, venue)
        self._require_remaining_orders(before, venue, progress)
        self._events.emit_reconciliation(venue)
        self._restore(context, venue.position.size_signed, progress)
        self._events.emit_state()
        if progress.stop_exit_required:
            self._close_remainder(venue, None)
        return True

    def resume_cleanup(
        self, records: list[dict[str, object]], venue: HyperliquidReconciliationSnapshot
    ) -> bool:
        """Restore only a proven completed exit, then finish exact residual cancellations."""
        cleanup = pending_protective_cleanup(records)
        if cleanup is None:
            return False
        validate_cleanup_suffix(records, cleanup)
        self._restore(
            cleanup.owner, cleanup.owner.position_size_signed, cleanup.owner.protective_progress
        )
        if cleanup.close_oid is not None:
            self._machine.acknowledge_close(cleanup.close_oid)
        finish_protective_cleanup(
            owner=self._machine.snapshot,
            completed=cleanup.completed,
            venue=venue,
            orders=self._orders,
            events=self._events,
            poller=self._poller,
            resuming=True,
            completion_recorded=cleanup.completion_recorded,
        )
        return True

    def _applies_to_restart(
        self,
        state: str,
        context: PendingPositionContext,
        venue: HyperliquidReconciliationSnapshot,
    ) -> bool:
        if context.protective_progress.stop_exit_required:
            return True
        if state == "EXIT_PENDING" or venue.position.size_signed == 0:
            return False
        return bool(context.protective_progress.fills) or (
            venue.position.size_signed != context.position_size_signed
        )

    def _restore(
        self,
        context: PendingPositionContext,
        size: float,
        progress: ProtectiveExecutionProgress,
    ) -> None:
        restore = (
            self._machine.restore_exit_pending
            if progress.stop_exit_required
            else self._machine.restore_protected_position
        )
        if context.stop_oid is None:
            raise AssetStartupReconciliationError("partial protective recovery lacks stop ownership")
        restore(
            entry_oid=context.entry_oid,
            stop_oid=context.stop_oid,
            target_oid=context.target_oid,
            target_price=context.target_price,
            position_size_signed=size,
            opened_at_ms=context.opened_at_ms,
            execution_plan=context.execution_plan,
            protective_progress=progress,
        )

    def _observe(
        self,
        before: AssetLiveSnapshot,
        venue: HyperliquidReconciliationSnapshot,
        close_oid: int | None = None,
    ) -> ProtectiveExecutionProgress:
        if before.stop_oid is None or before.opened_at_ms is None:
            raise AssetStartupReconciliationError("partial protection lacks original owned identity")
        try:
            return observe_protective_execution(
                previous_size_signed=before.position_size_signed,
                current_size_signed=venue.position.size_signed,
                opened_at_ms=before.opened_at_ms,
                observed_at_ms=int(self._now_fn().timestamp() * 1000),
                stop_oid=before.stop_oid,
                target_oid=before.target_oid,
                prior=before.protective_progress,
                fills=venue.fills,
                additional_exit_oids=() if close_oid is None else (close_oid,),
            )
        except ProtectiveExecutionEvidenceError as exc:
            raise AssetStartupReconciliationError(PARTIAL_PROTECTIVE_UNRESOLVED) from exc

    def _require_remaining_orders(
        self,
        before: AssetLiveSnapshot,
        venue: HyperliquidReconciliationSnapshot,
        progress: ProtectiveExecutionProgress,
    ) -> None:
        _require_owned_orders(before, venue)
        if not progress.stop_exit_required:
            verify_open_snapshot(
                replace(
                    before,
                    position_size_signed=venue.position.size_signed,
                    protective_progress=progress,
                ),
                venue,
            )

    def _checkpoint(
        self, venue: HyperliquidReconciliationSnapshot, progress: ProtectiveExecutionProgress
    ) -> None:
        self._events.emit_reconciliation(venue)
        self._machine.acknowledge_protective_execution(
            position_size_signed=venue.position.size_signed, progress=progress
        )
        self._events.emit_state()

    def _close_remainder(
        self, venue: HyperliquidReconciliationSnapshot, pending: PendingAssetOrderIntent | None
    ) -> HyperliquidReconciliationSnapshot:
        before = self._machine.snapshot
        _require_owned_orders(before, venue)
        if pending is None and venue.position.size_signed == 0:
            return self._finish(venue, self._observe(before, venue))
        if pending is None:
            observed = self._observe(before, venue)
            if observed != before.protective_progress:
                self._checkpoint(venue, observed)
                before = self._machine.snapshot
        ack = self._submit_or_recover(venue, pending)
        if not ack.accepted:
            return self._rejected_close(before)
        if ack.oid is None or ack.status not in {"filled", "canceled"}:
            raise AssetStartupReconciliationError("partial stop follow-up close is unresolved")
        self._machine.acknowledge_close(ack.oid)
        after = self._poller.wait_for(lambda current: self._explained(before, current, ack.oid))
        progress = self._observe(before, after, ack.oid)
        _require_owned_orders(before, after)
        if after.position.size_signed == 0:
            return self._finish(after, progress)
        self._checkpoint(after, progress)
        return after

    def _submit_or_recover(
        self, venue: HyperliquidReconciliationSnapshot, pending: PendingAssetOrderIntent | None
    ) -> HyperliquidOrderAck:
        if pending is None:
            self._events.emit_close_intent(
                reason="protective_stop_remainder",
                stop_oid=self._machine.snapshot.stop_oid or 0,
            )
            ack = self._orders.close_position(
                position_size_signed=venue.position.size_signed,
                mark_price=_position_reference(venue),
            )
            operation = "reduce_only_close"
        else:
            ack = self._orders.recover_existing_intent(
                operation="reduce_only_close", client_order_id=pending.client_order_id
            )
            operation = "reduce_only_close_restart_recovery"
        self._events.emit_ack(operation, ack, event_type="close")
        return ack

    def _explained(
        self, before: AssetLiveSnapshot, venue: HyperliquidReconciliationSnapshot, close_oid: int
    ) -> bool:
        try:
            progress = self._observe(before, venue, close_oid)
        except AssetStartupReconciliationError:
            return False
        return progress != before.protective_progress

    def _rejected_close(self, before: AssetLiveSnapshot) -> HyperliquidReconciliationSnapshot:
        after = self._poller.wait_for(
            lambda current: current.position.size_signed == 0
            or current.position.size_signed == before.position_size_signed
        )
        progress = self._observe(before, after)
        _require_owned_orders(before, after)
        if after.position.size_signed == 0:
            return self._finish(after, progress)
        if progress != before.protective_progress:
            self._checkpoint(after, progress)
        self._events.emit_reconciliation(after)
        self._events.emit_state()
        self._events.emit(
            "runtime_fault",
            {
                "reason": "protective stop follow-up close rejected",
                "exit_obligation_retained": True,
            },
        )
        return after

    def _finish(
        self, venue: HyperliquidReconciliationSnapshot, progress: ProtectiveExecutionProgress
    ) -> HyperliquidReconciliationSnapshot:
        before = self._machine.snapshot
        self._events.emit_reconciliation(venue)
        self._events.emit("close", cleanup_checkpoint_payload(before, progress))
        return finish_protective_cleanup(
            owner=before,
            completed=progress,
            venue=venue,
            orders=self._orders,
            events=self._events,
            poller=self._poller,
            resuming=False,
        )


def _context_snapshot(context: PendingPositionContext) -> AssetLiveSnapshot:
    return AssetLiveSnapshot(
        state=AssetLiveState.OPEN,
        entry_oid=context.entry_oid,
        stop_oid=context.stop_oid,
        target_oid=context.target_oid,
        target_price=context.target_price,
        position_size_signed=context.position_size_signed,
        opened_at_ms=context.opened_at_ms,
        execution_plan=context.execution_plan,
        protective_progress=context.protective_progress,
    )


def _require_owned_orders(before: AssetLiveSnapshot, venue: HyperliquidReconciliationSnapshot) -> None:
    ids = [order.oid for order in venue.open_orders]
    side = "A" if before.position_size_signed > 0 else "B"
    if (
        len(ids) != len(set(ids))
        or not set(ids).issubset({before.stop_oid, before.target_oid})
        or any(not order.reduce_only or order.side != side for order in venue.open_orders)
    ):
        raise AssetStartupReconciliationError(
            "partial protective recovery has unknown or conflicting orders"
        )


def _position_reference(venue: HyperliquidReconciliationSnapshot) -> float:
    size, value = venue.position.size_signed, venue.position.position_value_usd
    if not math.isfinite(size) or size == 0 or not math.isfinite(value) or value <= 0:
        raise AssetStartupReconciliationError(
            "partial stop close requires a valid reconciled position value"
        )
    price = value / abs(size)
    if not math.isfinite(price) or price <= 0:
        raise AssetStartupReconciliationError("partial stop close reference price is invalid")
    return price
