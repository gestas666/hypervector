"""Fail-closed live lifecycle for the frozen SOL range-onset canary."""

from __future__ import annotations
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
import time
from typing import NoReturn
from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_execution_plan import BoundExecutionPlan
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolLiveAdapterProtocol,
    SolReconciliationSnapshot,
)
from hypervector.live.sol_range_onset_config import SolRangeOnsetConfig
from hypervector.live.sol_range_onset_bracket_exit import reconcile_owned_bracket_exit
from hypervector.live.sol_range_onset_bracket_close import close_bracketed_position
from hypervector.live.sol_range_onset_consistency import (
    SolReconciliationPoller,
    protected_order_visible,
    protective_stop_fill_visible,
)
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_execution_plan import entry_notional
from hypervector.live.sol_range_onset_execution_plan import legacy_execution_plan
from hypervector.live.sol_range_onset_execution_plan import validate_entry_direction
from hypervector.live.sol_range_onset_engine_contract import (
    SolEntryNotFilledError,
    SolLiveEngineError,
    is_ioc_no_fill_error,
    require_started,
    resolve_decision_time_ms,
)
from hypervector.live.sol_range_onset_ledger import SolLiveLedger
from hypervector.live.sol_range_onset_live_telemetry import SolLiveTelemetry
from hypervector.live.sol_order_identity import new_client_order_id
from hypervector.live.sol_order_submission import SolOrderSubmission
from hypervector.live.sol_range_onset_startup import prepare_sol_live_startup
from hypervector.live.sol_range_onset_stop_close import close_stop_only_position
from hypervector.live.sol_range_onset_stop_entry import (
    place_and_verify_entry_protection,
)
from hypervector.live.sol_range_onset_verification import verify_open_snapshot
from hypervector.live.sol_range_onset_verification import verify_protected_position
from hypervector.live.sol_range_onset_reconcile import SolStartupReconciliationError
from hypervector.live.sol_range_onset_state import (
    SolLiveSnapshot,
    SolLiveState,
    SolLiveStateMachine,
)

_TELEMETRY_DEPTH_LEVELS = 20


class SolRangeOnsetLiveEngine:
    """Enforce one-position, protected-entry, and flat-before-reentry rules."""

    def __init__(
        self,
        *,
        config: SolRangeOnsetConfig,
        adapter: SolLiveAdapterProtocol,
        ledger: SolLiveLedger,
        credentials_present: bool,
        now_fn: Callable[[], datetime],
        reconciliation_attempts: int = 4,
        reconciliation_delay_seconds: float = 0.25,
        reconciliation_cache_invalidator: Callable[[], None] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        client_order_id_fn: Callable[[], str] = new_client_order_id,
    ) -> None:
        config.require_live_start(credentials_present=credentials_present)
        if Path(config.authoritative_ledger) != ledger.path:
            raise SolLiveEngineError("live engine ledger does not match config ledger")
        self._config = config
        self._adapter = adapter
        self._ledger = ledger
        self._now_fn = now_fn
        self._telemetry = SolLiveTelemetry(config=config, ledger=ledger, now_fn=now_fn)
        self._machine = SolLiveStateMachine()
        self._events = SolLiveEngineEvents(
            telemetry=self._telemetry, machine=self._machine
        )
        self._orders = SolOrderSubmission(
            adapter=adapter, events=self._events, client_order_id_fn=client_order_id_fn
        )
        self._poller = SolReconciliationPoller(
            adapter=adapter,
            attempts=reconciliation_attempts,
            delay_seconds=reconciliation_delay_seconds,
            sleep_fn=sleep_fn,
            before_retry=reconciliation_cache_invalidator,
        )
        self._started = False
        self._pending_execution_plan: BoundExecutionPlan | None = None

    @property
    def snapshot(self) -> SolLiveSnapshot:
        """Return the current immutable execution state."""
        return self._machine.snapshot

    def start(self) -> SolLiveSnapshot:
        """Run preflight and reconcile venue ownership before any strategy action."""
        if self._started:
            raise SolLiveEngineError("SOL live engine has already started")
        pending = prepare_sol_live_startup(
            config=self._config,
            adapter=self._adapter,
            ledger=self._ledger,
            machine=self._machine,
            events=self._events,
            orders=self._orders,
            poller=self._poller,
        )
        if pending is not None:
            self._protect_reconciled_entry(
                side=pending.side,
                mark_price=pending.mark_price,
                entry_ack=pending.ack,
                venue=pending.venue,
                opened_at_ms=pending.opened_at_ms,
            )
        self._started = True
        return self.snapshot

    def enter(
        self,
        *,
        side: str,
        mark_price: float,
        decision_time_ms: int | None = None,
        entry_sizing: CohortEntrySizing | None = None,
    ) -> SolLiveSnapshot:
        """Submit, reconcile, and protect one SOL entry before reporting OPEN."""
        require_started(self._started)
        if self.snapshot.state is not SolLiveState.FLAT:
            raise SolLiveEngineError(
                f"new entry requires FLAT, observed {self.snapshot.state.value}"
            )
        before = self._poller.wait_for_state(self.snapshot)
        if not before.is_flat:
            self._events.fault("entry refused because venue is not flat")
            raise SolLiveEngineError("entry refused because venue is not flat")
        notional = entry_notional(
            self._config,
            before.account.account_value_usd,
            fault=self._events.fault,
            sizing=entry_sizing,
        )
        ack, after_entry = self._submit_and_reconcile_entry(
            side=side,
            mark_price=mark_price,
            notional=notional,
        )
        return self._protect_reconciled_entry(
            side=side,
            mark_price=mark_price,
            entry_ack=ack,
            venue=after_entry,
            opened_at_ms=resolve_decision_time_ms(decision_time_ms, self._now_fn),
        )

    def _submit_and_reconcile_entry(
        self,
        *,
        side: str,
        mark_price: float,
        notional: float,
    ) -> tuple[HyperliquidOrderAck, SolReconciliationSnapshot]:
        plan = self._pending_execution_plan or legacy_execution_plan(self._config)
        self._machine.begin_entry(execution_plan=plan)
        self._events.emit_state()
        ack = self._orders.submit_entry(
            side=side,
            requested_notional_usd=notional,
            mark_price=mark_price,
        )
        self._events.emit_ack("entry", ack)
        if not ack.accepted or ack.oid is None:
            if _is_expected_ioc_no_fill(plan, ack):
                self._confirm_ioc_no_fill(ack)
            reason = f"entry rejected: {ack.error or ack.status}"
            self._events.fault(reason)
            raise SolLiveEngineError(reason)
        self._machine.acknowledge_entry(ack.oid)
        venue = self._poller.wait_for(
            lambda snapshot: snapshot.position.size_signed != 0.0
        )
        return ack, venue

    def _confirm_ioc_no_fill(self, ack: HyperliquidOrderAck) -> NoReturn:
        venue = self._poller.wait_for(lambda snapshot: snapshot.is_flat)
        self._events.emit_reconciliation(venue)
        if not venue.is_flat:
            reason = "IOC no-fill acknowledgement conflicts with venue exposure"
            self._events.fault(reason)
            raise SolLiveEngineError(reason)
        reason = f"IOC entry not filled: {ack.error}"
        self._events.confirm_entry_not_filled(reason=reason)
        raise SolEntryNotFilledError(reason)

    def _protect_reconciled_entry(
        self,
        *,
        side: str,
        mark_price: float,
        entry_ack: HyperliquidOrderAck,
        venue: SolReconciliationSnapshot,
        opened_at_ms: int,
    ) -> SolLiveSnapshot:
        if entry_ack.oid is None:
            raise SolLiveEngineError("accepted entry is missing venue order id")
        position = venue.position
        validate_entry_direction(
            side=side,
            observed_size=position.size_signed,
            mark_price=mark_price,
            fault=self._events.fault,
            emergency_flatten=self._emergency_flatten,
        )
        self._cancel_owned_entry_residual(entry_ack.oid, venue)
        self._machine.begin_protection(
            position_size_signed=position.size_signed,
            opened_at_ms=opened_at_ms,
        )
        self._events.emit_state()
        if position.entry_price is None:
            self._emergency_flatten(
                position_size_signed=position.size_signed,
                mark_price=mark_price,
                reason="entry price missing during stop calculation",
            )
        plan = self.snapshot.execution_plan or legacy_execution_plan(self._config)
        side_name = "long" if position.size_signed > 0.0 else "short"
        trigger = plan.stop_price(
            entry_price=position.entry_price,
            side=side_name,
        )
        return place_and_verify_entry_protection(
            config=self._config,
            entry_oid=entry_ack.oid,
            position_size_signed=position.size_signed,
            trigger_price=trigger,
            mark_price=mark_price,
            machine=self._machine,
            events=self._events,
            orders=self._orders,
            poller=self._poller,
            emergency_flatten=self._emergency_flatten,
        )

    def exit(self, *, mark_price: float, reason: str) -> SolLiveSnapshot:
        """Cancel owned protection, reduce-only close, and verify flat."""
        require_started(self._started)
        if self.snapshot.state is not SolLiveState.OPEN:
            raise SolLiveEngineError(
                f"exit requires OPEN, observed {self.snapshot.state.value}"
            )
        before = self._poller.wait_for_state(self.snapshot)
        snapshot = self.snapshot
        verify_open_snapshot(snapshot, before)
        if snapshot.target_oid is not None:
            return close_bracketed_position(
                snapshot=snapshot,
                venue=before,
                mark_price=mark_price,
                reason=reason,
                machine=self._machine,
                events=self._events,
                orders=self._orders,
                poller=self._poller,
            )
        return close_stop_only_position(
            snapshot=snapshot,
            venue=before,
            mark_price=mark_price,
            reason=reason,
            machine=self._machine,
            events=self._events,
            orders=self._orders,
            poller=self._poller,
            restore_missing_protection=self._restore_missing_protection,
        )

    def stop(self, reason: str) -> SolLiveSnapshot:
        """Stop process evaluation while preserving venue-native protection."""
        self._machine.stop(reason)
        self._events.emit_state()
        return self.snapshot

    def reconcile_telemetry(
        self,
        *,
        funding_start_time_ms: int,
        funding_end_time_ms: int,
    ) -> SolReconciliationSnapshot:
        """Refresh authoritative exposure, fills, fees, and funding payments."""
        require_started(self._started)
        venue = self._poller.wait_for_state(self.snapshot)
        try:
            if (
                self.snapshot.state is SolLiveState.OPEN
                and reconcile_owned_bracket_exit(
                    snapshot=self.snapshot,
                    venue=venue,
                    orders=self._orders,
                    events=self._events,
                    poller=self._poller,
                )
            ):
                pass
            elif protective_stop_fill_visible(self.snapshot, venue):
                self._events.confirm_protective_stop_fill(
                    stop_oid=self.snapshot.stop_oid or 0
                )
            elif self.snapshot.state is SolLiveState.OPEN:
                verify_open_snapshot(self.snapshot, venue)
            elif self.snapshot.state is SolLiveState.FLAT and not venue.is_flat:
                raise SolStartupReconciliationError(
                    "venue is not flat while local lifecycle is FLAT"
                )
        except SolStartupReconciliationError as exc:
            self._events.fault(f"continuous reconciliation failed: {exc}")
            raise SolLiveEngineError(str(exc)) from exc
        self._events.emit_reconciliation(venue)
        self._telemetry.emit_book(
            self._adapter.book_snapshot(depth_levels=_TELEMETRY_DEPTH_LEVELS)
        )
        payments = self._adapter.funding_payments(
            start_time_ms=funding_start_time_ms,
            end_time_ms=funding_end_time_ms,
        )
        self._telemetry.emit_funding_payments(payments)
        return venue

    def record_strategy_decision(self, payload: dict[str, object]) -> None:
        """Persist one causal strategy decision and its theoretical quote."""
        require_started(self._started)
        plan = payload.get("execution_plan")
        if plan is not None:
            self._pending_execution_plan = BoundExecutionPlan.from_payload(plan)
        self._events.emit("regime_decision", payload)
        self._events.emit(
            "theoretical_quote",
            {
                "decision_time_ms": payload.get("decision_time_ms"),
                "reference_price": payload.get("reference_price"),
            },
        )

    def _cancel_owned_entry_residual(
        self,
        entry_oid: int,
        venue: SolReconciliationSnapshot,
    ) -> None:
        non_reduce = [order for order in venue.open_orders if not order.reduce_only]
        if any(order.oid != entry_oid for order in non_reduce):
            self._emergency_flatten(
                position_size_signed=venue.position.size_signed,
                mark_price=venue.position.entry_price or 0.0,
                reason="unknown non-reduce-only order appeared after entry",
            )
        for order in non_reduce:
            cancel = self._orders.cancel_order(order.oid)
            self._events.emit_ack("entry_residual_cancel", cancel)
            if not cancel.accepted:
                self._emergency_flatten(
                    position_size_signed=venue.position.size_signed,
                    mark_price=venue.position.entry_price or 0.0,
                    reason=f"entry residual cancel rejected: {cancel.error or cancel.status}",
                )

    def _restore_missing_protection(
        self,
        venue: SolReconciliationSnapshot,
        trigger_price: float | None,
    ) -> bool:
        if venue.position.size_signed == 0.0 or trigger_price is None:
            return False
        ack = self._orders.place_protective_stop(
            position_size_signed=venue.position.size_signed,
            trigger_price=trigger_price,
        )
        self._events.emit_ack(
            "replacement_protective_stop", ack, event_type="stop_order"
        )
        return self._finish_missing_protection(venue, ack)

    def _finish_missing_protection(
        self,
        venue: SolReconciliationSnapshot,
        ack: HyperliquidOrderAck,
    ) -> bool:
        if not ack.accepted or ack.oid is None or self.snapshot.entry_oid is None:
            return False
        protected = self._poller.wait_for(
            lambda current: protected_order_visible(
                current,
                stop_oid=ack.oid or 0,
                position_size_signed=venue.position.size_signed,
            )
            or current.position.size_signed == 0.0
        )
        try:
            stop_filled = verify_protected_position(
                entry_oid=self.snapshot.entry_oid or 0,
                stop_oid=ack.oid,
                position_size_signed=venue.position.size_signed,
                opened_at_ms=self.snapshot.opened_at_ms,
                venue=protected,
            )
        except SolStartupReconciliationError:
            return False
        self._events.emit_reconciliation(protected)
        if stop_filled:
            self._events.confirm_stop_fill_during_exit(stop_oid=ack.oid)
            return True
        self._machine.restore_protection_after_exit_failure(stop_oid=ack.oid)
        self._events.emit_state()
        return True

    def _emergency_flatten(
        self,
        *,
        position_size_signed: float,
        mark_price: float,
        reason: str,
        stop_oid: int | None = None,
    ) -> NoReturn:
        if stop_oid is not None:
            cancel = self._orders.cancel_order(stop_oid)
            self._events.emit_ack("emergency_stop_cancel", cancel)
        close = self._orders.close_position(
            position_size_signed=position_size_signed,
            mark_price=mark_price,
        )
        self._events.emit_ack(
            "emergency_reduce_only_close",
            close,
            event_type="close",
        )
        after = self._poller.wait_for(lambda snapshot: snapshot.is_flat)
        suffix = (
            "" if after.position.size_signed == 0.0 else "; emergency close not flat"
        )
        failure = reason + suffix
        self._events.fault(failure)
        raise SolLiveEngineError(failure)


def _is_expected_ioc_no_fill(
    plan: BoundExecutionPlan,
    ack: HyperliquidOrderAck,
) -> bool:
    """Recognize only Hyperliquid's definitive IOC no-match acknowledgement."""
    return bool(
        plan.entry_liquidity == "taker_ioc"
        and not ack.accepted
        and ack.oid is None
        and ack.status == "error"
        and ack.error is not None
        and is_ioc_no_fill_error(ack.error)
    )
