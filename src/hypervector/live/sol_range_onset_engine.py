"""Fail-closed live lifecycle for the frozen SOL range-onset canary."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime

from hyperliquid.utils.error import ClientError, ServerError
from requests.exceptions import RequestException
from pathlib import Path
from typing import NoReturn

from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_execution_plan import BoundExecutionPlan
from hypervector.live.entry_submission_deadline import (
    EntryDeadlineExpired,
    EntrySubmissionDeadline,
)
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolLiveAdapterProtocol,
    SolBookSnapshot,
    SolReconciliationSnapshot,
)
from hypervector.live.sol_order_identity import new_client_order_id
from hypervector.live.sol_entry_read_recovery import (
    EntryReconciliationUnavailable,
    EntrySubmissionRuntime,
)
from hypervector.live.sol_order_submission import SolOrderSubmission
from hypervector.live.sol_range_onset_bracket_close import close_bracketed_position
from hypervector.live.sol_range_onset_bracket_exit import reconcile_owned_bracket_exit
from hypervector.live.sol_range_onset_config import SolRangeOnsetConfig
from hypervector.live.sol_range_onset_consistency import (
    SolReconciliationPoller,
    protected_order_visible,
    protective_stop_fill_visible,
)
from hypervector.live.sol_range_onset_engine_contract import (
    STOP_ALREADY_AT_TARGET,
    SolEntryNotFilledError as SolEntryNotFilledError,
    SolLiveEngineError,
    StopRaiseOutcome,
    require_started,
    resolve_decision_time_ms,
    stop_rests_at_or_beyond,
)
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_execution_plan import (
    entry_notional,
    legacy_execution_plan,
    validate_entry_direction,
)
from hypervector.live.sol_range_onset_ledger import SolLiveLedger
from hypervector.live.sol_range_onset_live_telemetry import SolLiveTelemetry
from hypervector.live.sol_range_onset_reconcile import SolStartupReconciliationError
from hypervector.live.sol_range_onset_startup import prepare_sol_live_startup
from hypervector.live.sol_range_onset_state import (
    SolLiveSnapshot,
    SolLiveState,
    SolLiveStateMachine,
)
from hypervector.live.sol_range_onset_stop_close import close_stop_only_position
from hypervector.live.sol_range_onset_stop_entry import (
    place_and_verify_entry_protection,
)
from hypervector.live.sol_range_onset_verification import (
    verify_canceled_entry_exposure,
    verify_open_snapshot,
    verify_protected_position,
)
from hypervector.live.sol_partial_protective_recovery import (
    SolPartialProtectiveRecovery,
)
from hypervector.live.sol_protective_execution_evidence import (
    ProtectiveExecutionEvidenceError,
)
from hypervector.live.cohort_stop_risk_sizing import (
    StopRiskAccountValueError,
    size_for_stop_risk,
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
            adapter=adapter,
            events=self._events,
            client_order_id_fn=client_order_id_fn,
            sleep_fn=sleep_fn,
        )
        self._poller = SolReconciliationPoller(
            adapter=adapter,
            attempts=reconciliation_attempts,
            delay_seconds=reconciliation_delay_seconds,
            sleep_fn=sleep_fn,
            before_retry=reconciliation_cache_invalidator,
        )
        self._started = False
        self._latest_book: SolBookSnapshot | None = None
        self._partial_protective = SolPartialProtectiveRecovery(
            machine=self._machine,
            events=self._events,
            orders=self._orders,
            poller=self._poller,
            now_fn=self._now_fn,
        )
        self._pending_execution_plan: BoundExecutionPlan | None = None
        self._entry_submission = EntrySubmissionRuntime(
            config, self._machine, self._events, self._orders, self._poller
        )

    @property
    def snapshot(self) -> SolLiveSnapshot:
        """Return the current immutable execution state."""
        return self._machine.snapshot

    @property
    def latest_book(self) -> SolBookSnapshot | None:
        """Return the last reconciled read-only book without another network call."""
        return self._latest_book

    def start(self) -> SolLiveSnapshot:
        """Run preflight and reconcile venue ownership before any strategy action."""
        if self._started:
            raise SolLiveEngineError("SOL live engine has already started")
        pending = prepare_sol_live_startup(
            partial_protective=self._partial_protective,
            emergency_flatten=self._emergency_flatten,
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
        entry_deadline: EntrySubmissionDeadline | None = None,
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
        return self._enter_with_protection(
            side=side,
            mark_price=mark_price,
            notional=notional,
            entry_deadline=entry_deadline,
            decision_time_ms=decision_time_ms,
            account_value_usd=before.account.account_value_usd,
        )

    def _enter_with_protection(
        self,
        *,
        side: str,
        mark_price: float,
        notional: float,
        decision_time_ms: int | None,
        entry_deadline: EntrySubmissionDeadline | None = None,
        account_value_usd: float | None = None,
    ) -> SolLiveSnapshot:
        plan = self._pending_execution_plan or legacy_execution_plan(self._config)
        if plan.stop_risk_budget is not None:
            try:
                risk = size_for_stop_risk(
                    plan=plan,
                    budget=plan.stop_risk_budget,
                    mark_price=mark_price,
                    side=side,
                    entry_slippage_fraction=self._config.effective_entry_slippage_cap_fraction,
                    original_notional_usd=notional,
                    account_value_usd=account_value_usd,
                )
            except StopRiskAccountValueError as exc:
                # An equity-fraction budget never sizes on a guessed equity; the
                # entry is refused as a journaled technical failure.
                self._pending_execution_plan = None
                reason = f"entry refused: {exc}"
                self._events.fault(reason)
                raise SolLiveEngineError(reason) from exc
            self._events.emit("entry_stop_risk_sizing", risk.as_payload())
            notional = risk.notional_usd
        try:
            ack, venue = self._entry_submission.submit_and_reconcile(
                side=side,
                mark_price=mark_price,
                notional=notional,
                plan=plan,
                entry_deadline=entry_deadline,
            )
        except EntryDeadlineExpired:
            self._pending_execution_plan = None
            raise
        except EntryReconciliationUnavailable as failure:
            return self._entry_submission.protect_after_read_failure(
                failure=failure,
                side=side,
                mark_price=mark_price,
                opened_at_ms=resolve_decision_time_ms(decision_time_ms, self._now_fn),
                emergency_flatten=self._emergency_flatten,
            )
        return self._protect_reconciled_entry(
            side=side,
            mark_price=mark_price,
            entry_ack=ack,
            venue=venue,
            opened_at_ms=resolve_decision_time_ms(decision_time_ms, self._now_fn),
        )

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
        verify_canceled_entry_exposure(entry_ack, venue, self._events.fault)
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
        if plan.structural_anchor_overrun(position.entry_price, side_name):
            self._events.emit(
                "structural_anchor_overrun",
                {
                    "entry_price": position.entry_price,
                    "side": side_name,
                    "stop_anchor": plan.stop_anchor,
                    "applied_stop_bps": plan.minimum_stop_bps,
                    "source": "entry_protection",
                },
            )
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

    def normalize_trigger_price(self, trigger_price: float) -> float:
        """Return the trigger as this engine's stop orders put it on the wire."""
        return self._orders.normalize_trigger_price(trigger_price)

    def raise_protective_stop(self, *, trigger_price: float) -> bool | StopRaiseOutcome:
        """Move the owned reduce-only stop to a more favorable trigger while staying OPEN.

        Returns True only after the venue shows the replacement covering the
        position. A rejected replacement leaves the original stop untouched and
        returns False; it never faults the process on its own. The target is
        compared with the venue trigger on the adapter's wire price grid: when
        the owned stop already rests at or beyond the wire-rounded target, no
        venue call is made and the falsy STOP_ALREADY_AT_TARGET is returned.
        """
        require_started(self._started)
        snapshot = self.snapshot
        if snapshot.state is not SolLiveState.OPEN or snapshot.stop_oid is None:
            return False
        venue = self._poller.wait_for_state(snapshot)
        venue = self._reconcile_owned_lifecycle(venue)
        snapshot = self.snapshot
        if snapshot.state is not SolLiveState.OPEN or snapshot.stop_oid is None:
            return False
        current = next(
            (order for order in venue.open_orders if order.oid == snapshot.stop_oid),
            None,
        )
        size = snapshot.position_size_signed
        if current is None or current.trigger_price is None or size == 0.0:
            return False
        wire_target = self._orders.normalize_trigger_price(trigger_price)
        if stop_rests_at_or_beyond(current.trigger_price, wire_target, size):
            return STOP_ALREADY_AT_TARGET
        previous_oid = snapshot.stop_oid
        ack = self._orders.modify_protective_stop(
            oid=previous_oid, position_size_signed=size, trigger_price=trigger_price
        )
        self._events.emit_ack("protective_stop_raise", ack, event_type="stop_order")
        if not ack.accepted or ack.oid is None:
            return False
        self._machine.replace_protection(stop_oid=ack.oid)
        self._events.emit_state()
        protected = self._poller.wait_for(
            lambda latest: protected_order_visible(
                latest, stop_oid=ack.oid or 0, position_size_signed=size
            )
            or latest.position.size_signed == 0.0
        )
        self._events.emit_reconciliation(protected)
        self._events.emit(
            "protective_stop_raised",
            {
                "previous_stop_oid": previous_oid,
                "stop_oid": ack.oid,
                "previous_trigger_price": current.trigger_price,
                "trigger_price": trigger_price,
                "position_size_signed": size,
                "venue_visible": protected.position.size_signed != 0.0,
            },
        )
        return True

    def exit(self, *, mark_price: float, reason: str) -> SolLiveSnapshot:
        """Cancel owned protection, reduce-only close, and verify flat."""
        require_started(self._started)
        if self.snapshot.state is not SolLiveState.OPEN:
            raise SolLiveEngineError(
                f"exit requires OPEN, observed {self.snapshot.state.value}"
            )
        before = self._poller.wait_for_state(self.snapshot)
        before = self._reconcile_owned_lifecycle(before)
        if self.snapshot.state is not SolLiveState.OPEN:
            return self.snapshot
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
        venue = self._reconcile_owned_lifecycle(venue)
        self._events.emit_reconciliation(venue)
        book = self._adapter.book_snapshot(depth_levels=_TELEMETRY_DEPTH_LEVELS)
        self._telemetry.emit_book(book)
        self._latest_book = book
        payments = self._adapter.funding_payments(
            start_time_ms=funding_start_time_ms,
            end_time_ms=funding_end_time_ms,
        )
        self._telemetry.emit_funding_payments(payments)
        return venue

    def _reconcile_owned_lifecycle(
        self, venue: SolReconciliationSnapshot
    ) -> SolReconciliationSnapshot:
        try:
            partial = self._partial_protective.reconcile(venue)
            if partial is not None:
                venue = partial
            bracket_exit = (
                reconcile_owned_bracket_exit(
                    snapshot=self.snapshot,
                    venue=venue,
                    orders=self._orders,
                    events=self._events,
                    poller=self._poller,
                )
                if self.snapshot.state is SolLiveState.OPEN
                else None
            )
            if bracket_exit is not None:
                venue = bracket_exit
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
        except (SolStartupReconciliationError, ProtectiveExecutionEvidenceError) as exc:
            self._events.fault(f"continuous reconciliation failed: {exc}")
            raise SolLiveEngineError(str(exc)) from exc
        except (RequestException, ClientError, ServerError) as exc:
            raise SolLiveEngineError(
                "lifecycle reconciliation failed during an order-capable operation; "
                "recover the durable order identity before resuming"
            ) from exc
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
