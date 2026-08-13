"""Reconciled target-only lifecycle for the BTC 5m source-follow canary."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import time

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolBookSnapshot,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)
from hypervector.live.source_follow_live_config import SourceFollowLiveConfig
from hypervector.live.source_follow_live_ledger import SourceFollowLiveLedger
from hypervector.live.source_follow_live_models import (
    SourceFollowLiveSnapshot,
    SourceFollowLiveState,
)
from hypervector.live.source_follow_live_protocol import SourceFollowVenueProtocol
from hypervector.live.source_follow_live_reconcile import (
    duration_reached,
    opened_at_ms,
    target_fill_matches,
    target_matches,
    target_price,
    wait_for_flat,
    wait_for_target,
)
from hypervector.live.source_follow_live_telemetry import SourceFollowLiveTelemetry
from hypervector.regime.source_follow_runtime import SourceFollowDecision


class SourceFollowLiveEngineError(RuntimeError):
    """The BTC live lifecycle cannot reconcile or preserve its contract."""


class SourceFollowLiveEngine:
    """Own one BTC position and its reduce-only target from venue truth."""

    def __init__(
        self,
        *,
        config: SourceFollowLiveConfig,
        adapter: SourceFollowVenueProtocol,
        ledger: SourceFollowLiveLedger,
        credentials_present: bool,
        now_fn: Callable[[], datetime],
        client_order_id_fn: Callable[[], str],
        reconciliation_attempts: int = 4,
        reconciliation_delay_seconds: float = 0.25,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        config.require_live_start(credentials_present=credentials_present)
        if config.backend_ledger != ledger.path:
            raise SourceFollowLiveEngineError(
                "engine ledger does not match live config"
            )
        self._config = config
        self._adapter = adapter
        self._telemetry = SourceFollowLiveTelemetry(
            config=config,
            ledger=ledger,
            now_fn=now_fn,
        )
        self._now_fn = now_fn
        self._client_order_id_fn = client_order_id_fn
        if reconciliation_attempts < 1 or reconciliation_delay_seconds < 0.0:
            raise SourceFollowLiveEngineError("invalid reconciliation retry policy")
        self._reconciliation_attempts = reconciliation_attempts
        self._reconciliation_delay_seconds = reconciliation_delay_seconds
        self._sleep_fn = sleep_fn
        self._snapshot = SourceFollowLiveSnapshot(SourceFollowLiveState.FLAT)
        self._started = False
        self._last_decision_at: datetime | None = None
        self._funding_cursor_ms = 0

    @property
    def snapshot(self) -> SourceFollowLiveSnapshot:
        """Return current immutable venue lifecycle state."""
        return self._snapshot

    def start(self) -> SourceFollowLiveSnapshot:
        """Preflight, set leverage while flat, and reconcile before decisions."""
        if self._started:
            raise SourceFollowLiveEngineError(
                "source-follow live engine already started"
            )
        preflight = self._adapter.preflight(
            expected_max_leverage=self._config.expected_max_leverage
        )
        self._validate_preflight(preflight)
        if preflight.position.size_signed == 0.0:
            self._adapter.configure_isolated_leverage(int(self._config.leverage))
        venue = self._adapter.reconcile()
        self._telemetry.emit_preflight(preflight, venue)
        self._telemetry.emit_book(self._adapter.book_snapshot(depth_levels=5))
        self._funding_cursor_ms = max(0, self._timestamp_ms() - 86_400_000)
        self._started = True
        return self._reconcile_lifecycle(venue)

    def process(
        self,
        decision: SourceFollowDecision | None,
    ) -> SourceFollowLiveSnapshot:
        """Reconcile one cycle, then consume at most one fresh source decision."""
        if not self._started:
            raise SourceFollowLiveEngineError(
                "source-follow live engine is not started"
            )
        venue = self._adapter.reconcile()
        self._telemetry.emit_reconciliation(venue)
        self._emit_funding()
        if self._snapshot.state is not SourceFollowLiveState.FAULT:
            self._reconcile_lifecycle(venue)
        book = self._adapter.book_snapshot(depth_levels=5)
        self._telemetry.emit_book(book)
        if decision is not None:
            self._consume_decision(decision)
        if decision is not None and self._snapshot.state is SourceFollowLiveState.FLAT:
            self._submit_entry(decision, venue, book)
        return self._snapshot

    def record_history(self, decisions: tuple[SourceFollowDecision, ...]) -> None:
        """Publish bounded measured history without entering the execution path."""
        if not self._started:
            raise SourceFollowLiveEngineError(
                "source-follow live engine is not started"
            )
        for decision in decisions:
            self._telemetry.emit_history(decision)

    def _validate_preflight(self, preflight: SolVenuePreflight) -> None:
        position = preflight.position
        if position.size_signed > 0.0 and not self._allows_long:
            raise SourceFollowLiveEngineError("source-follow canary refuses a BTC long")
        if position.size_signed != 0.0 and (
            position.leverage_type != "isolated"
            or position.leverage != int(self._config.leverage)
        ):
            raise SourceFollowLiveEngineError(
                "existing BTC position must be isolated at configured leverage"
            )

    def _reconcile_lifecycle(
        self,
        venue: SolReconciliationSnapshot,
    ) -> SourceFollowLiveSnapshot:
        position = venue.position
        if position.size_signed > 0.0 and not self._allows_long:
            return self._fault("venue reports a BTC long position")
        if position.size_signed != 0.0:
            return self._reconcile_open_position(venue)

        if venue.open_orders:
            opening = tuple(
                order for order in venue.open_orders if not order.reduce_only
            )
            if len(opening) == 1 and len(venue.open_orders) == 1:
                if duration_reached(
                    observed_at_ms=self._timestamp_ms(),
                    started_at_ms=opening[0].timestamp_ms,
                    duration_seconds=self._config.entry_ttl_seconds,
                ):
                    ack = self._adapter.cancel_order(opening[0].oid)
                    self._telemetry.emit_ack("cancel_expired_entry", ack)
                    if not ack.accepted:
                        return self._fault("expired BTC entry cancellation failed")
                    return self._set_state(SourceFollowLiveState.FLAT)
                return self._set_state(
                    SourceFollowLiveState.ENTRY_PENDING,
                    entry_oid=opening[0].oid,
                )
            return self._fault("flat BTC venue state contains unexpected orders")
        self._emit_verified_target_close(venue)
        return self._set_state(SourceFollowLiveState.FLAT)

    def _reconcile_open_position(
        self,
        venue: SolReconciliationSnapshot,
    ) -> SourceFollowLiveSnapshot:
        if self._snapshot.state is SourceFollowLiveState.EXIT_PENDING:
            return self._snapshot
        residual_failure = self._cancel_entry_residuals(venue)
        if residual_failure is not None:
            return self._fault(residual_failure)
        refreshed = self._adapter.reconcile()
        opened = opened_at_ms(
            refreshed,
            snapshot_opened_at_ms=self._snapshot.opened_at_ms,
            fallback_ms=self._timestamp_ms(),
        )
        if duration_reached(
            observed_at_ms=self._timestamp_ms(),
            started_at_ms=opened,
            duration_seconds=self._config.maximum_hold_seconds,
        ):
            return self._maximum_hold_exit(refreshed)
        targets = tuple(order for order in refreshed.open_orders if order.reduce_only)
        if len(targets) > 1:
            return self._fault("venue reports multiple BTC reduce-only targets")
        if not targets:
            return self._place_target(refreshed, opened_at_ms=opened)
        target = targets[0]
        if not target_matches(refreshed.position.size_signed, target):
            return self._fault("BTC target does not match reconciled exposure")
        return self._set_state(
            SourceFollowLiveState.OPEN_TARGET_RESTING,
            entry_oid=self._snapshot.entry_oid,
            target_oid=target.oid,
            position_size=refreshed.position.size_signed,
            opened_at_ms=opened,
        )

    def _emit_verified_target_close(
        self,
        venue: SolReconciliationSnapshot,
    ) -> None:
        if self._snapshot.state is not SourceFollowLiveState.OPEN_TARGET_RESTING:
            return
        self._emit_target_close(
            venue,
            target_oid=self._snapshot.target_oid,
            position_size=self._snapshot.position_size_signed,
        )

    def _emit_target_close(
        self,
        venue: SolReconciliationSnapshot,
        *,
        target_oid: int | None,
        position_size: float,
    ) -> None:
        if target_fill_matches(
            venue,
            target_oid=target_oid,
            position_size=position_size,
        ):
            self._telemetry.emit(
                "close",
                {"reason": "target", "oid": target_oid, "verified_flat": True},
            )

    def _emit_funding(self) -> None:
        end_ms = self._timestamp_ms()
        payments = self._adapter.funding_payments(
            start_time_ms=self._funding_cursor_ms,
            end_time_ms=end_ms,
        )
        self._telemetry.emit_funding_payments(payments)
        self._funding_cursor_ms = end_ms

    def _maximum_hold_exit(
        self,
        venue: SolReconciliationSnapshot,
    ) -> SourceFollowLiveSnapshot:
        for order in venue.open_orders:
            ack = self._adapter.cancel_order(order.oid)
            self._telemetry.emit_ack("cancel_target_for_maximum_hold", ack)
            if not ack.accepted:
                return self._fault("target cancellation failed at maximum hold")
        return self._close_and_confirm_flat(
            reason="maximum_hold",
            operation="maximum_hold_close",
        )

    def _cancel_entry_residuals(
        self,
        venue: SolReconciliationSnapshot,
    ) -> str | None:
        for order in venue.open_orders:
            if order.reduce_only:
                continue
            ack = self._adapter.cancel_order(order.oid)
            self._telemetry.emit_ack("cancel_entry_residual", ack)
            if not ack.accepted:
                return "entry residual cancellation failed"
        return None

    def _place_target(
        self,
        venue: SolReconciliationSnapshot,
        *,
        opened_at_ms: int,
    ) -> SourceFollowLiveSnapshot:
        position = venue.position
        if position.entry_price is None:
            return self._fault("open BTC position has no venue entry price")
        price = target_price(
            entry_price=position.entry_price,
            position_size=position.size_signed,
            target_margin_pct=self._config.target_margin_pct,
            leverage=self._config.leverage,
        )
        self._telemetry.emit_order_intent(
            operation="target",
            side="sell" if position.size_signed > 0.0 else "buy",
            quantity_or_notional=abs(position.size_signed),
            limit_price=price,
        )
        ack = self._adapter.submit_target(
            position_size_signed=position.size_signed,
            limit_price=price,
            client_order_id=self._client_order_id_fn(),
        )
        self._telemetry.emit_target_ack(ack, price)
        return self._confirm_target(
            ack=ack,
            position_size=position.size_signed,
            opened_at_ms=opened_at_ms,
        )

    def _confirm_target(
        self,
        *,
        ack: HyperliquidOrderAck,
        position_size: float,
        opened_at_ms: int,
    ) -> SourceFollowLiveSnapshot:
        """Verify target ownership or recover by closing confirmed exposure."""
        if not ack.accepted or ack.oid is None:
            return self._close_and_confirm_flat(
                reason="target_submission_failure",
                operation="target_failure_close",
            )
        confirmed = wait_for_target(
            self._adapter,
            target_oid=ack.oid,
            attempts=self._reconciliation_attempts,
            delay_seconds=self._reconciliation_delay_seconds,
            sleep_fn=self._sleep_fn,
        )
        self._telemetry.emit_reconciliation(confirmed)
        if confirmed.position.size_signed == 0.0:
            self._emit_target_close(
                confirmed,
                target_oid=ack.oid,
                position_size=position_size,
            )
            return self._set_state(SourceFollowLiveState.FLAT)
        if not any(order.oid == ack.oid for order in confirmed.open_orders):
            return self._fault(
                "accepted BTC target is not visible after reconciliation"
            )
        return self._set_state(
            SourceFollowLiveState.OPEN_TARGET_RESTING,
            entry_oid=self._snapshot.entry_oid,
            target_oid=ack.oid,
            position_size=position_size,
            opened_at_ms=opened_at_ms,
        )

    def _close_and_confirm_flat(
        self,
        *,
        reason: str,
        operation: str,
    ) -> SourceFollowLiveSnapshot:
        latest = self._adapter.reconcile()
        self._telemetry.emit_reconciliation(latest)
        if latest.position.size_signed == 0.0:
            self._emit_verified_target_close(latest)
            return self._set_state(SourceFollowLiveState.FLAT)
        mark = self._adapter.book_snapshot(depth_levels=1).mid_price
        self._telemetry.emit(
            "close",
            {"reason": reason, "intent": True, "mark_price": mark},
        )
        ack = self._adapter.close_position(
            position_size_signed=latest.position.size_signed,
            mark_price=mark,
            client_order_id=self._client_order_id_fn(),
        )
        self._telemetry.emit_ack(operation, ack, event_type="close")
        if not ack.accepted:
            return self._fault(f"{reason} close rejected: {ack.error or ack.status}")
        confirmed = wait_for_flat(
            self._adapter,
            attempts=self._reconciliation_attempts,
            delay_seconds=self._reconciliation_delay_seconds,
            sleep_fn=self._sleep_fn,
        )
        self._telemetry.emit_reconciliation(confirmed)
        if confirmed.position.size_signed != 0.0:
            return self._fault(f"{reason} close did not reconcile flat")
        self._telemetry.emit(
            "close",
            {"reason": reason, "oid": ack.oid, "verified_flat": True},
        )
        return self._set_state(SourceFollowLiveState.FLAT)

    def _consume_decision(self, decision: SourceFollowDecision) -> None:
        if (
            self._last_decision_at is not None
            and decision.available_at_utc <= self._last_decision_at
        ):
            raise SourceFollowLiveEngineError(
                "source decisions must be strictly increasing"
            )
        self._last_decision_at = decision.available_at_utc
        self._telemetry.emit_decision(decision)

    def _submit_entry(
        self,
        decision: SourceFollowDecision,
        venue: SolReconciliationSnapshot,
        book: SolBookSnapshot,
    ) -> None:
        direction = decision.entry_direction
        if not decision.entry_eligible or direction is None:
            return
        if direction == "long" and not self._allows_long:
            return
        notional = min(
            venue.account.account_value_usd
            * self._config.margin_fraction
            * self._config.leverage,
            self._config.max_notional_usd,
        )
        price = book.bids[0].price if direction == "long" else book.asks[0].price
        self._telemetry.emit_order_intent(
            operation="entry",
            side="buy" if direction == "long" else "sell",
            quantity_or_notional=notional,
            limit_price=price,
        )
        ack = self._adapter.submit_entry(
            side=direction,
            requested_notional_usd=notional,
            limit_price=price,
            client_order_id=self._client_order_id_fn(),
        )
        self._telemetry.emit_ack("entry", ack)
        if not ack.accepted or ack.oid is None:
            self._fault(f"entry rejected: {ack.error or ack.status}")
            return
        self._set_state(SourceFollowLiveState.ENTRY_PENDING, entry_oid=ack.oid)

    def _fault(self, reason: str) -> SourceFollowLiveSnapshot:
        self._telemetry.emit("fault", {"reason": reason})
        return self._set_state(
            SourceFollowLiveState.FAULT,
            entry_oid=self._snapshot.entry_oid,
            target_oid=self._snapshot.target_oid,
            position_size=self._snapshot.position_size_signed,
            opened_at_ms=self._snapshot.opened_at_ms,
            last_fault=reason,
        )

    def _set_state(
        self,
        state: SourceFollowLiveState,
        *,
        entry_oid: int | None = None,
        target_oid: int | None = None,
        position_size: float = 0.0,
        opened_at_ms: int | None = None,
        last_fault: str | None = None,
    ) -> SourceFollowLiveSnapshot:
        self._snapshot = SourceFollowLiveSnapshot(
            state,
            entry_oid,
            target_oid,
            position_size,
            opened_at_ms,
            last_fault,
        )
        self._telemetry.emit_lifecycle(
            state=state.value,
            entry_oid=entry_oid,
            target_oid=target_oid,
            position_size_signed=position_size,
            opened_at_ms=opened_at_ms,
            last_fault=last_fault,
        )
        return self._snapshot

    def _timestamp_ms(self) -> int:
        now = self._now_fn()
        if now.tzinfo is None or now.utcoffset() is None:
            raise SourceFollowLiveEngineError("engine clock must be timezone-aware")
        return int(now.timestamp() * 1_000)

    @property
    def _allows_long(self) -> bool:
        return self._config.profile.direction_mode == "source_follow_bidirectional"
