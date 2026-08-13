"""Fail-closed dual-bracket lifecycle for the Hulk Smash BTC canary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
import time

from hypervector.live.hulk_smash_live_close import (
    HulkSmashCloseError,
    HulkSmashCloseResult,
)
from hypervector.live.hulk_smash_live_components import (
    build_hulk_smash_live_components,
)
from hypervector.live.hulk_smash_live_config import HulkSmashLiveConfig
from hypervector.live.hulk_smash_live_checks import (
    HulkSmashLiveCheckError,
    filled_exit_reason,
    filled_oid,
    maximum_hold_reached,
    validate_short_position,
)
from hypervector.live.hulk_smash_live_decisions import HulkSmashLiveDecision
from hypervector.live.hulk_smash_live_entry import (
    HulkSmashEntryError,
    HulkSmashEntryExposureError,
)
from hypervector.live.hulk_smash_live_ledger import HulkSmashLiveLedger
from hypervector.live.hulk_smash_live_models import (
    HulkSmashLiveSnapshot,
    HulkSmashLiveState,
)
from hypervector.live.hulk_smash_live_orders import (
    HulkSmashOrderError,
)
from hypervector.live.hulk_smash_live_protocol import HulkSmashVenueProtocol
from hypervector.live.hulk_smash_live_risk import (
    HulkProtectionPlan,
    build_hulk_protection_plan,
)
from hypervector.live.hulk_smash_live_restart import (
    HulkSmashRestartError,
    has_bracket,
    has_stop,
    restore_hulk_owned_snapshot,
    restore_hulk_snapshot,
)
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolReconciliationSnapshot,
)

_FUNDING_LOOKBACK_MS = 86_400_000


class HulkSmashLiveEngineError(RuntimeError):
    """The Hulk live lifecycle cannot preserve owned, protected exposure."""


class HulkSmashLiveEngine:
    """Own one short BTC position with an exact stop and target bracket."""

    def __init__(
        self,
        *,
        config: HulkSmashLiveConfig,
        adapter: HulkSmashVenueProtocol,
        ledger: HulkSmashLiveLedger,
        credentials_present: bool,
        now_fn: Callable[[], datetime],
        client_order_id_fn: Callable[[], str],
        reconciliation_attempts: int = 4,
        reconciliation_delay_seconds: float = 0.25,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        config.require_live_start(credentials_present=credentials_present)
        if config.backend_ledger != ledger.path:
            raise HulkSmashLiveEngineError("engine ledger differs from config")
        if reconciliation_attempts < 1 or reconciliation_delay_seconds < 0.0:
            raise HulkSmashLiveEngineError("invalid reconciliation retry policy")
        self._config = config
        self._adapter = adapter
        self._ledger = ledger
        components = build_hulk_smash_live_components(
            config=config,
            adapter=adapter,
            ledger=ledger,
            now_fn=now_fn,
            client_order_id_fn=client_order_id_fn,
            attempts=reconciliation_attempts,
            delay_seconds=reconciliation_delay_seconds,
            sleep_fn=sleep_fn,
        )
        self._telemetry = components.telemetry
        self._reconciler = components.reconciler
        self._orders = components.orders
        self._closer = components.closer
        self._entry = components.entry
        self._now_fn = now_fn
        self._snapshot = HulkSmashLiveSnapshot()
        self._started = False
        self._funding_cursor_ms = 0
        self._last_close_reason: str | None = None

    @property
    def snapshot(self) -> HulkSmashLiveSnapshot:
        """Return current immutable venue ownership state."""
        return self._snapshot

    @property
    def last_close_reason(self) -> str | None:
        """Return the latest venue-verified close attribution."""
        return self._last_close_reason

    def start(self) -> HulkSmashLiveSnapshot:
        """Preflight and reconcile exact bracket ownership before any signal."""
        if self._started:
            raise HulkSmashLiveEngineError("Hulk live engine already started")
        prior = self._ledger.read_all()
        prior_owned = self._prior_owned_snapshot(prior)
        if prior_owned is not None:
            self._telemetry.claim_order_ids(
                tuple(
                    oid
                    for oid in (
                        prior_owned.entry_oid,
                        prior_owned.stop_oid,
                        prior_owned.target_oid,
                    )
                    if oid is not None
                )
            )
        self._set_state(HulkSmashLiveState.PREFLIGHT)
        preflight = self._adapter.preflight(
            expected_max_leverage=int(self._config.venue_max_leverage)
        )
        venue = self._adapter.reconcile()
        self._telemetry.emit_preflight(preflight, venue)
        self._validate_position(venue)
        if venue.position.size_signed == 0.0:
            if prior_owned is not None:
                self._snapshot = prior_owned
                self._complete_flat(venue)
            elif venue.open_orders:
                self._fault_and_raise("flat BTC account contains unowned open orders")
            self._adapter.configure_isolated_leverage(int(self._config.leverage))
            if prior_owned is None:
                self._set_state(HulkSmashLiveState.FLAT)
        else:
            self._restore_open(prior, venue)
        self._telemetry.emit_book(self._adapter.book_snapshot(depth_levels=5))
        self._funding_cursor_ms = max(0, self._timestamp_ms() - _FUNDING_LOOKBACK_MS)
        if prior_owned is not None and prior_owned.opened_at_ms is not None:
            self._funding_cursor_ms = min(
                self._funding_cursor_ms,
                prior_owned.opened_at_ms,
            )
        self._started = True
        return self._snapshot

    def record_strategy_decision(self, decision: HulkSmashLiveDecision) -> None:
        """Persist one causal strategy decision before any venue mutation."""
        self._require_started()
        self._telemetry.emit_decision(decision)

    def record_history(self, decisions: tuple[HulkSmashLiveDecision, ...]) -> None:
        """Persist bounded warmup decisions without historical execution."""
        self._require_started()
        self._telemetry.emit_history_batch(decisions)

    def enter(self, decision: HulkSmashLiveDecision) -> HulkSmashLiveSnapshot:
        """Submit one short entry, then verify stop and target at the venue."""
        self._require_started()
        if self._snapshot.state is not HulkSmashLiveState.FLAT:
            raise HulkSmashLiveEngineError("Hulk entry requires FLAT state")
        if not decision.entry_eligible or decision.stop_anchor is None:
            raise HulkSmashLiveEngineError("Hulk entry requires an eligible decision")
        before = self._adapter.reconcile()
        if not before.is_flat:
            self._fault_and_raise("entry refused because BTC venue is not flat")
        initial = build_hulk_protection_plan(
            entry_price=decision.reference_price,
            stop_anchor=decision.stop_anchor,
            account_equity_usd=before.account.account_value_usd,
            config=self._config,
        )
        self._set_state(HulkSmashLiveState.ENTRY_PENDING)
        try:
            entry = self._entry.submit(initial, decision)
            self._snapshot = replace(self._snapshot, entry_oid=entry.oid)
            self._emit_state()
            opened = self._entry.confirm(entry)
        except HulkSmashEntryExposureError as exc:
            self._emergency_flatten(str(exc), exc.venue)
        except HulkSmashEntryError as exc:
            self._fault_and_raise(str(exc))
        self._validate_position(opened)
        return self._protect_opened(entry, opened, decision)

    def poll_market(self) -> HulkSmashLiveSnapshot:
        """Reconcile bracket state, fills, funding, book, and maximum hold."""
        self._require_started()
        venue = self._adapter.reconcile()
        self._telemetry.emit_reconciliation(venue)
        self._funding_cursor_ms = self._telemetry.emit_market_snapshot(
            adapter=self._adapter,
            funding_start_ms=self._funding_cursor_ms,
            observed_at_ms=self._timestamp_ms(),
        )
        if self._snapshot.state is HulkSmashLiveState.OPEN:
            if venue.position.size_signed == 0.0:
                self._complete_flat(venue)
            else:
                self._validate_open_bracket(venue)
                if (
                    self._snapshot.state is HulkSmashLiveState.OPEN
                    and self._maximum_hold_reached()
                ):
                    self._close_open("maximum_hold", venue)
        return self._snapshot

    def stop(self, reason: str) -> HulkSmashLiveSnapshot:
        """Stop evaluation while preserving any verified venue-native bracket."""
        self._require_started()
        message = reason.strip()
        if not message:
            raise HulkSmashLiveEngineError("stop reason must be non-empty")
        if self._snapshot.state not in {
            HulkSmashLiveState.FLAT,
            HulkSmashLiveState.OPEN,
        }:
            raise HulkSmashLiveEngineError("engine cannot stop in transient state")
        self._set_state(HulkSmashLiveState.STOPPED)
        return self._snapshot

    def _protect_opened(
        self,
        entry: HyperliquidOrderAck,
        venue: SolReconciliationSnapshot,
        decision: HulkSmashLiveDecision,
    ) -> HulkSmashLiveSnapshot:
        position = venue.position
        if (
            position.entry_price is None
            or entry.oid is None
            or decision.stop_anchor is None
        ):
            self._emergency_flatten(
                "entry reconciliation lacks price or identity", venue
            )
        try:
            plan = build_hulk_protection_plan(
                entry_price=position.entry_price,
                stop_anchor=decision.stop_anchor,
                account_equity_usd=venue.account.account_value_usd,
                config=self._config,
                position_notional_usd=abs(position.size_signed * position.entry_price),
            )
        except ValueError as exc:
            self._emergency_flatten(f"postfill risk plan invalid: {exc}", venue)
        self._telemetry.emit_protection_plan(plan.as_payload())
        self._snapshot = HulkSmashLiveSnapshot(
            state=HulkSmashLiveState.PROTECTING,
            entry_oid=entry.oid,
            position_size_signed=position.size_signed,
            opened_at_ms=decision.decision_time_ms,
            entry_price=position.entry_price,
            stop_price=plan.stop_price,
            target_price=plan.target_price,
        )
        self._emit_state()
        stopped = self._place_stop(plan, venue)
        if stopped is None:
            return self._snapshot
        return self._place_target(plan, stopped)

    def _place_stop(
        self,
        plan: HulkProtectionPlan,
        venue: SolReconciliationSnapshot,
    ) -> SolReconciliationSnapshot | None:
        try:
            ack = self._orders.place_stop(plan, venue)
        except HulkSmashOrderError as exc:
            self._emergency_flatten(str(exc), venue)
        self._snapshot = replace(self._snapshot, stop_oid=ack.oid)
        self._emit_state()
        return self._wait_for_protection(
            lambda current: has_stop(current, ack.oid or 0),
            "protective stop not venue-visible",
        )

    def _place_target(
        self,
        plan: HulkProtectionPlan,
        venue: SolReconciliationSnapshot,
    ) -> HulkSmashLiveSnapshot:
        try:
            ack = self._orders.place_target(plan, venue)
        except HulkSmashOrderError as exc:
            self._emergency_flatten(str(exc), venue)
        self._snapshot = replace(self._snapshot, target_oid=ack.oid)
        self._emit_state()
        bracketed = self._wait_for_protection(
            lambda current: has_bracket(
                current,
                self._snapshot.stop_oid or 0,
                ack.oid or 0,
            ),
            "complete bracket not venue-visible",
        )
        if bracketed is None:
            return self._snapshot
        venue_prices = _venue_bracket_prices(
            bracketed,
            self._snapshot.stop_oid or 0,
            ack.oid or 0,
        )
        if venue_prices is None:
            self._emergency_flatten(
                "venue bracket lacks exact stop or target price",
                bracketed,
            )
        stop_price, target_price = venue_prices
        self._snapshot = replace(
            self._snapshot,
            state=HulkSmashLiveState.OPEN,
            position_size_signed=bracketed.position.size_signed,
            stop_price=stop_price,
            target_price=target_price,
        )
        self._telemetry.emit_reconciliation(bracketed)
        self._emit_state()
        return self._snapshot

    def _complete_flat(self, venue: SolReconciliationSnapshot) -> None:
        owned = {self._snapshot.stop_oid, self._snapshot.target_oid} - {None}
        unknown = [order.oid for order in venue.open_orders if order.oid not in owned]
        if unknown:
            self._fault_and_raise(
                f"flat reconciliation contains unknown orders: {unknown}"
            )
        for order in venue.open_orders:
            self._cancel_order(order.oid, "cancel_residual_bracket")
        if venue.open_orders:
            venue = self._wait_for(lambda current: current.is_flat)
        try:
            reason = filled_exit_reason(self._snapshot, venue)
        except HulkSmashLiveCheckError as exc:
            self._fault_and_raise(str(exc))
        self._last_close_reason = reason
        self._telemetry.emit_close(
            {
                "reason": reason,
                "verified_flat": True,
                "oid": filled_oid(self._snapshot, venue),
            }
        )
        self._snapshot = HulkSmashLiveSnapshot(state=HulkSmashLiveState.FLAT)
        self._telemetry.emit_reconciliation(venue)
        self._emit_state()

    def _validate_open_bracket(self, venue: SolReconciliationSnapshot) -> None:
        self._validate_position(venue)
        if has_bracket(
            venue,
            self._snapshot.stop_oid or 0,
            self._snapshot.target_oid or 0,
        ):
            return
        recovered = self._wait_for(
            lambda current: current.position.size_signed == 0.0
            or has_bracket(
                current,
                self._snapshot.stop_oid or 0,
                self._snapshot.target_oid or 0,
            )
        )
        if recovered.position.size_signed == 0.0:
            self._complete_flat(recovered)
            return
        if not has_bracket(
            recovered,
            self._snapshot.stop_oid or 0,
            self._snapshot.target_oid or 0,
        ):
            self._emergency_flatten("owned BTC bracket is incomplete", recovered)

    def _close_open(self, reason: str, venue: SolReconciliationSnapshot) -> None:
        self._set_state(HulkSmashLiveState.EXIT_PENDING)
        try:
            result = self._closer.close_scheduled(self._snapshot, venue)
        except (HulkSmashCloseError, HulkSmashOrderError) as exc:
            self._fault_and_raise(str(exc))
        if result.bracket_exit:
            self._complete_flat(result.venue)
            return
        self._finish_close(reason, result)

    def _finish_close(self, reason: str, result: HulkSmashCloseResult) -> None:
        self._last_close_reason = reason
        self._telemetry.emit_close(
            {
                "reason": reason,
                "oid": result.oid,
                "verified_flat": True,
                "response_ambiguous": result.response_ambiguous,
            }
        )
        self._snapshot = HulkSmashLiveSnapshot(state=HulkSmashLiveState.FLAT)
        self._telemetry.emit_reconciliation(result.venue)
        self._emit_state()

    def _emergency_flatten(
        self,
        reason: str,
        venue: SolReconciliationSnapshot,
    ) -> None:
        try:
            result = self._closer.close_emergency(self._snapshot, venue)
        except (HulkSmashCloseError, HulkSmashOrderError) as exc:
            self._fault_and_raise(f"{reason}; {exc}")
        self._telemetry.emit_close(
            {
                "reason": "emergency_flatten",
                "oid": result.oid,
                "verified_flat": True,
                "response_ambiguous": result.response_ambiguous,
            }
        )
        self._snapshot = HulkSmashLiveSnapshot(
            state=HulkSmashLiveState.FAULTED,
            last_fault=reason,
        )
        self._telemetry.emit_reconciliation(result.venue)
        self._telemetry.emit_fault(reason)
        self._emit_state()
        raise HulkSmashLiveEngineError(reason)

    def _restore_open(
        self,
        records: list[dict[str, object]],
        venue: SolReconciliationSnapshot,
    ) -> None:
        try:
            self._snapshot = restore_hulk_snapshot(
                records,
                profile_fingerprint=self._config.profile_fingerprint,
                venue=venue,
            )
        except HulkSmashRestartError as exc:
            self._fault_and_raise(str(exc))
        self._emit_state()

    def _prior_owned_snapshot(
        self,
        records: list[dict[str, object]],
    ) -> HulkSmashLiveSnapshot | None:
        try:
            return restore_hulk_owned_snapshot(
                records,
                self._config.profile_fingerprint,
            )
        except HulkSmashRestartError as exc:
            self._fault_and_raise(str(exc))

    def _validate_position(self, venue: SolReconciliationSnapshot) -> None:
        try:
            validate_short_position(venue, leverage=int(self._config.leverage))
        except HulkSmashLiveCheckError as exc:
            self._fault_and_raise(str(exc))

    def _cancel_order(self, oid: int, operation: str) -> None:
        try:
            self._orders.cancel_order(oid, operation)
        except HulkSmashOrderError as exc:
            self._fault_and_raise(str(exc))

    def _wait_for_protection(
        self,
        predicate: Callable[[SolReconciliationSnapshot], bool],
        failure_reason: str,
    ) -> SolReconciliationSnapshot | None:
        result = self._reconciler.until(
            lambda venue: venue.position.size_signed == 0.0 or predicate(venue)
        )
        if not result.matched:
            self._emergency_flatten(failure_reason, result.snapshot)
        if result.snapshot.position.size_signed == 0.0:
            self._complete_flat(result.snapshot)
            return None
        return result.snapshot

    def _wait_for(
        self,
        predicate: Callable[[SolReconciliationSnapshot], bool],
    ) -> SolReconciliationSnapshot:
        result = self._reconciler.until(predicate)
        if result.matched:
            return result.snapshot
        raise HulkSmashLiveEngineError("venue reconciliation did not converge")

    def _maximum_hold_reached(self) -> bool:
        try:
            return maximum_hold_reached(
                self._snapshot,
                now_ms=self._timestamp_ms(),
                maximum_hold_seconds=self._config.maximum_hold_seconds,
            )
        except HulkSmashLiveCheckError as exc:
            self._fault_and_raise(str(exc))

    def _set_state(self, state: HulkSmashLiveState) -> None:
        self._snapshot = replace(self._snapshot, state=state)
        self._emit_state()

    def _emit_state(self) -> None:
        self._telemetry.emit_state(self._snapshot.as_payload())

    def _fault_and_raise(self, reason: str) -> None:
        self._snapshot = replace(
            self._snapshot,
            state=HulkSmashLiveState.FAULTED,
            last_fault=reason,
        )
        self._telemetry.emit_fault(reason)
        self._emit_state()
        raise HulkSmashLiveEngineError(reason)

    def _require_started(self) -> None:
        if not self._started:
            raise HulkSmashLiveEngineError("Hulk live engine is not started")

    def _timestamp_ms(self) -> int:
        value = self._now_fn()
        if value.tzinfo is None or value.utcoffset() is None:
            raise HulkSmashLiveEngineError("engine clock must be timezone-aware")
        return int(value.timestamp() * 1_000)


def _venue_bracket_prices(
    venue: SolReconciliationSnapshot,
    stop_oid: int,
    target_oid: int,
) -> tuple[float, float] | None:
    stop = next((order for order in venue.open_orders if order.oid == stop_oid), None)
    target = next(
        (order for order in venue.open_orders if order.oid == target_oid), None
    )
    if (
        stop is None
        or target is None
        or stop.trigger_price is None
        or target.limit_price is None
    ):
        return None
    return stop.trigger_price, target.limit_price
