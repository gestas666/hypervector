"""Reconciled paired-quote lifecycle for the Apex MM live canary."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from functools import partial
import time

from hypervector.live.apex_mm_live_config import ApexMMLiveConfig
from hypervector.live.apex_mm_live_models import ApexMMLiveSnapshot, ApexMMLiveState
from hypervector.live.apex_mm_live_market import ApexMMMarketTracker
from hypervector.live.apex_mm_live_orders import (
    quote_replacement_required,
    recovered_cancel_ack,
    recovered_order_ack,
)
from hypervector.live.apex_mm_live_protocol import (
    ApexMMTelemetryProtocol,
    ApexMMVenueProtocol,
)
from hypervector.live.apex_mm_streaming_venue import ApexMMStreamingVenueError
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
    HyperliquidPostOnlyOrder,
    SolBookSnapshot,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)
from hypervector.live.hyperliquid_sol_parsing import (
    HyperliquidAdapterError,
    HyperliquidOrderUnavailableError,
)
from hypervector.live.sol_order_transport import (
    HyperliquidBatchOrderTransportError,
    SolCancelTransportError,
    SolOrderTransportError,
)
from hypervector.research.apex_regime_mm_policy import (
    ApexMMMarketState,
    ApexMMPolicyConfig,
    ApexMMQuote,
    quote_apex_regime_mm_v2,
)

_RECOVERY_ATTEMPTS = 4
_RECOVERY_DELAY_SECONDS = 0.25
_FUNDING_POLL_INTERVAL_MS = 3_600_000


def _stale_quote(quote: ApexMMQuote) -> ApexMMQuote:
    return ApexMMQuote(
        active=False,
        reason="stale_book",
        fair_value=quote.fair_value,
        bid_price=None,
        ask_price=None,
        bid_size=0.0,
        ask_size=0.0,
        full_spread_bps=0.0,
        inventory_utilization=quote.inventory_utilization,
    )


class ApexMMLiveEngineError(RuntimeError):
    """The MM lifecycle cannot reconcile or preserve its live contract."""


class ApexMMLiveEngine:
    """Own paired BTC maker quotes and one-way net venue inventory."""

    def __init__(
        self,
        *,
        config: ApexMMLiveConfig,
        adapter: ApexMMVenueProtocol,
        telemetry: ApexMMTelemetryProtocol,
        credentials_present: bool,
        now_fn: Callable[[], datetime],
        client_order_id_fn: Callable[[], str],
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        config.require_live_start(credentials_present=credentials_present)
        self._config = config
        self._adapter = adapter
        self._telemetry = telemetry
        self._now_fn = now_fn
        self._client_order_id_fn = client_order_id_fn
        self._sleep_fn = sleep_fn
        self._snapshot = ApexMMLiveSnapshot(ApexMMLiveState.STARTING)
        self._started = False
        self._maker_fee_rate: float | None = None
        self._price_tick: float | None = None
        self._funding_cursor_ms = 0
        self._next_funding_poll_ms = 0
        self._market_tracker = ApexMMMarketTracker()

    @property
    def snapshot(self) -> ApexMMLiveSnapshot:
        """Return the current immutable venue lifecycle state."""
        return self._snapshot

    @property
    def cleanup_required(self) -> bool:
        """Return whether this engine may still own live venue exposure."""
        return self._started and self._snapshot.state is not ApexMMLiveState.STOPPED

    def start(self) -> ApexMMLiveSnapshot:
        """Preflight a flat account, configure leverage, and place one quote pair."""
        if self._started:
            raise ApexMMLiveEngineError("Apex MM live engine already started")
        try:
            preflight = self._adapter.preflight(
                expected_max_leverage=self._config.expected_max_leverage
            )
            venue = self._adapter.reconcile()
            self._require_flat_start(preflight, venue)
            self._adapter.configure_isolated_leverage(self._config.leverage)
            self._maker_fee_rate = preflight.fees.maker_rate
            self._price_tick = preflight.price_tick
            self._funding_cursor_ms = max(0, self._timestamp_ms() - 3_600_000)
            self._telemetry.emit_preflight(preflight, venue)
            self._started = True
            return self._replace_quotes(venue)
        except (ApexMMStreamingVenueError, HyperliquidAdapterError) as exc:
            return self._fault(f"venue state failure: {exc}")

    def process(self) -> ApexMMLiveSnapshot:
        """Reconcile fills and inventory, then refresh quotes when required."""
        try:
            return self._process_once()
        except (ApexMMStreamingVenueError, HyperliquidAdapterError) as exc:
            return self._fault(f"venue state failure: {exc}")
        except ApexMMLiveEngineError as exc:
            return self._fault(str(exc))

    def _process_once(self) -> ApexMMLiveSnapshot:
        self._require_running()
        venue = self._adapter.reconcile()
        self._telemetry.emit_reconciliation(venue)
        self._emit_funding()
        book = self._adapter.book_snapshot(depth_levels=self._config.depth_levels)
        self._telemetry.emit_book(book)
        self._validate_position(venue)
        inventory_notional = abs(venue.position.size_signed) * book.mid_price
        if inventory_notional > self._config.max_inventory_notional_usd + 1e-9:
            return self._fault_and_flatten(
                "inventory notional cap breached", venue, book
            )
        expected = {
            oid for oid in (self._snapshot.bid_oid, self._snapshot.ask_oid) if oid
        }
        observed = {order.oid for order in venue.open_orders}
        expired = self._quote_expired()
        candidate = self._quote(venue, book)
        self._telemetry.emit_quote(
            candidate,
            venue.position.size_signed * book.mid_price,
        )
        changed = quote_replacement_required(
            open_orders=venue.open_orders,
            quote=candidate,
            current_position_size=venue.position.size_signed,
            quoted_position_size=self._snapshot.position_size_signed,
        )
        if observed != expected or (expired and changed):
            return self._replace_quotes(venue)
        return self._set_active_state(venue)

    def shutdown(self) -> ApexMMLiveSnapshot:
        """Cancel every quote, flatten residual inventory, and verify flat."""
        self._require_running(allow_fault=True)
        self._adapter.begin_shutdown()
        venue = self._adapter.reconcile()
        self._cancel_orders(venue)
        venue = self._adapter.reconcile()
        if venue.position.size_signed != 0.0:
            book = self._adapter.book_snapshot(depth_levels=1)
            self._close_position(venue, book, "operator_stop")
        confirmed = self._adapter.reconcile()
        self._telemetry.emit_reconciliation(confirmed)
        if not confirmed.is_flat:
            raise ApexMMLiveEngineError("operator stop did not reconcile flat")
        return self._set_snapshot(ApexMMLiveSnapshot(ApexMMLiveState.STOPPED))

    def _replace_quotes(
        self,
        venue: SolReconciliationSnapshot,
    ) -> ApexMMLiveSnapshot:
        self._cancel_orders(venue)
        confirmed = self._adapter.reconcile()
        self._telemetry.emit_reconciliation(confirmed)
        if confirmed.open_orders:
            return self._fault("quote cancellation did not reconcile empty")
        fresh_book = self._adapter.book_snapshot(depth_levels=self._config.depth_levels)
        self._telemetry.emit_book(fresh_book)
        quote = self._quote(confirmed, fresh_book)
        inventory_notional = confirmed.position.size_signed * fresh_book.mid_price
        self._telemetry.emit_quote(quote, inventory_notional)
        acknowledgements, quote_expired, submitted_at_ms = self._submit_quote_legs(
            quote,
            book_exchange_timestamp_ms=fresh_book.exchange_timestamp_ms,
        )
        if quote_expired:
            return self._withhold_expired_pair(quote, acknowledgements)
        if not acknowledgements:
            state = (
                ApexMMLiveState.INVENTORY
                if confirmed.position.size_signed != 0.0
                else ApexMMLiveState.QUOTING
            )
            return self._set_snapshot(
                ApexMMLiveSnapshot(
                    state=state,
                    position_size_signed=confirmed.position.size_signed,
                )
            )
        if any(not ack.accepted or ack.oid is None for _, ack in acknowledgements):
            self._rollback_acknowledged(acknowledgements)
            return self._fault("paired post-only quote submission failed")
        if submitted_at_ms is None:
            raise ApexMMLiveEngineError("active quote batch has no submission time")
        return self._confirm_quotes(confirmed, acknowledgements, submitted_at_ms)

    def _quote(
        self,
        venue: SolReconciliationSnapshot,
        book: SolBookSnapshot,
    ) -> ApexMMQuote:
        if self._maker_fee_rate is None or self._price_tick is None:
            raise ApexMMLiveEngineError("venue fee and tick are unavailable")
        equity = venue.account.account_value_usd
        if equity <= 0.0:
            raise ApexMMLiveEngineError("account equity must be positive")
        maximum_fraction = min(
            self._config.max_inventory_notional_usd / equity,
            1.0,
        )
        policy = ApexMMPolicyConfig(
            tick_size=self._price_tick,
            maker_fee_rate=self._maker_fee_rate,
            maximum_inventory_fraction=maximum_fraction,
            base_order_notional_usd=self._config.base_order_notional_usd,
            minimum_order_notional_usd=self._config.minimum_order_notional_usd,
            maximum_book_age_ms=self._config.maximum_book_age_ms,
        )
        return quote_apex_regime_mm_v2(self._market_state(venue, book, equity), policy)

    def _market_state(
        self,
        venue: SolReconciliationSnapshot,
        book: SolBookSnapshot,
        equity: float,
    ) -> ApexMMMarketState:
        observation = self._market_tracker.observe(book)
        book_age = max(0, self._timestamp_ms() - book.exchange_timestamp_ms)
        return ApexMMMarketState(
            best_bid=book.bids[0].price,
            best_ask=book.asks[0].price,
            best_bid_size=book.bids[0].size,
            best_ask_size=book.asks[0].size,
            volatility_bps=observation.volatility_bps,
            inventory_qty=venue.position.size_signed,
            equity_usd=equity,
            book_age_ms=book_age,
            cascade_side=observation.cascade_side,
        )

    def _submit_quote_legs(
        self,
        quote: ApexMMQuote,
        *,
        book_exchange_timestamp_ms: int,
    ) -> tuple[list[tuple[str, HyperliquidOrderAck]], bool, int | None]:
        legs = (
            ("buy", quote.bid_price, quote.bid_size),
            ("sell", quote.ask_price, quote.ask_size),
        )
        requests: list[HyperliquidPostOnlyOrder] = []
        for side, price, size in legs:
            if price is None or size <= 0.0:
                continue
            notional = price * size
            client_order_id = self._client_order_id_fn()
            requests.append(
                HyperliquidPostOnlyOrder(
                    side=side,
                    requested_notional_usd=notional,
                    limit_price=price,
                    client_order_id=client_order_id,
                )
            )
        if not requests:
            return [], False, None
        if self._quote_snapshot_expired(book_exchange_timestamp_ms):
            return [], True, None
        submitted_at_ms = self._timestamp_ms()
        quote_batch_id = requests[0].client_order_id
        for request in requests:
            self._telemetry.emit_order_intent(
                operation="maker_quote",
                side=request.side,
                quantity_or_notional=request.requested_notional_usd,
                limit_price=request.limit_price,
                client_order_id=request.client_order_id,
                quote_batch_id=quote_batch_id,
                book_exchange_timestamp_ms=book_exchange_timestamp_ms,
                batch_submission_started_at_ms=submitted_at_ms,
            )
        try:
            acknowledgements = self._adapter.submit_post_only_batch(tuple(requests))
        except HyperliquidBatchOrderTransportError as exc:
            expected_ids = tuple(request.client_order_id for request in requests)
            if exc.client_order_ids != expected_ids:
                raise ApexMMLiveEngineError(
                    "batch transport identities do not match quote intents"
                ) from exc
            acknowledgements = tuple(
                recovered_order_ack(self._recover_client_status(identity))
                for identity in expected_ids
            )
        if len(acknowledgements) != len(requests):
            raise ApexMMLiveEngineError(
                "post-only batch acknowledgement count does not match quote legs"
            )
        results = list(
            zip(
                (request.side for request in requests),
                acknowledgements,
                strict=True,
            )
        )
        for side, acknowledgement in results:
            self._telemetry.emit_ack(f"quote_{side}", acknowledgement)
        return results, False, submitted_at_ms

    def _quote_snapshot_expired(self, exchange_timestamp_ms: int) -> bool:
        age_ms = max(0, self._timestamp_ms() - exchange_timestamp_ms)
        return age_ms > self._config.maximum_book_age_ms

    def _withhold_expired_pair(
        self,
        quote: ApexMMQuote,
        acknowledgements: list[tuple[str, HyperliquidOrderAck]],
    ) -> ApexMMLiveSnapshot:
        self._rollback_acknowledged(acknowledgements)
        confirmed = self._adapter.reconcile()
        self._telemetry.emit_reconciliation(confirmed)
        if confirmed.open_orders:
            return self._fault("stale quote rollback did not reconcile empty")
        if confirmed.position.size_signed != 0.0:
            book = self._adapter.book_snapshot(depth_levels=1)
            self._telemetry.emit_book(book)
            return self._fault_and_flatten(
                "stale quote filled during paired submission", confirmed, book
            )
        self._telemetry.emit_quote(_stale_quote(quote), 0.0)
        return self._set_snapshot(ApexMMLiveSnapshot(ApexMMLiveState.QUOTING))

    def _confirm_quotes(
        self,
        venue: SolReconciliationSnapshot,
        acknowledgements: list[tuple[str, HyperliquidOrderAck]],
        submitted_at_ms: int,
    ) -> ApexMMLiveSnapshot:
        confirmed = self._adapter.reconcile()
        self._telemetry.emit_reconciliation(confirmed)
        expected = {ack.oid for _, ack in acknowledgements if ack.oid is not None}
        observed = {order.oid for order in confirmed.open_orders}
        if expected != observed:
            self._cancel_orders(confirmed)
            return self._fault("accepted quote identities did not reconcile")
        by_side = {side: ack.oid for side, ack in acknowledgements}
        return self._set_snapshot(
            ApexMMLiveSnapshot(
                ApexMMLiveState.INVENTORY
                if venue.position.size_signed != 0.0
                else ApexMMLiveState.QUOTING,
                bid_oid=by_side.get("buy"),
                ask_oid=by_side.get("sell"),
                position_size_signed=venue.position.size_signed,
                quote_started_at_ms=submitted_at_ms,
            )
        )

    def _cancel_orders(self, venue: SolReconciliationSnapshot) -> None:
        for order in venue.open_orders:
            self._telemetry.emit_order_intent(
                operation="cancel_quote",
                oid=order.oid,
                side=order.side,
                quantity_or_notional=order.size,
                limit_price=order.limit_price or 0.0,
            )
            ack = self._cancel_order(order.oid)
            self._telemetry.emit_ack("cancel_quote", ack)
            if not ack.accepted:
                raise ApexMMLiveEngineError(
                    f"quote cancel rejected for oid {order.oid}"
                )

    def _rollback_acknowledged(
        self,
        acknowledgements: list[tuple[str, HyperliquidOrderAck]],
    ) -> None:
        for _, acknowledgement in acknowledgements:
            if not acknowledgement.accepted or acknowledgement.oid is None:
                continue
            self._telemetry.emit_order_intent(
                operation="rollback_quote",
                oid=acknowledgement.oid,
            )
            cancel = self._cancel_order(acknowledgement.oid)
            self._telemetry.emit_ack("rollback_quote", cancel)
            if not cancel.accepted:
                raise ApexMMLiveEngineError("paired quote rollback failed")

    def _fault_and_flatten(
        self,
        message: str,
        venue: SolReconciliationSnapshot,
        book: SolBookSnapshot,
    ) -> ApexMMLiveSnapshot:
        self._cancel_orders(venue)
        latest = self._adapter.reconcile()
        if latest.position.size_signed != 0.0:
            self._close_position(latest, book, "inventory_cap")
        confirmed = self._adapter.reconcile()
        self._telemetry.emit_reconciliation(confirmed)
        if not confirmed.is_flat:
            raise ApexMMLiveEngineError("inventory fault did not reconcile flat")
        return self._fault(message)

    def _close_position(
        self,
        venue: SolReconciliationSnapshot,
        book: SolBookSnapshot,
        reason: str,
    ) -> None:
        client_order_id = self._client_order_id_fn()
        self._telemetry.emit_order_intent(
            operation=f"close_{reason}",
            side="sell" if venue.position.size_signed > 0.0 else "buy",
            quantity_or_notional=abs(venue.position.size_signed) * book.mid_price,
            limit_price=book.mid_price,
            client_order_id=client_order_id,
        )
        try:
            ack = self._adapter.close_position(
                position_size_signed=venue.position.size_signed,
                mark_price=book.mid_price,
                client_order_id=client_order_id,
            )
        except SolOrderTransportError as exc:
            ack = recovered_order_ack(self._recover_client_status(exc.client_order_id))
        self._telemetry.emit_ack(f"close_{reason}", ack)
        if not ack.accepted or ack.oid is None:
            raise ApexMMLiveEngineError(f"{reason} close was rejected")
        closed, markout = self._adapter.wait_for_fill(
            ack.oid, self._config.markout_horizon_ms
        )
        self._telemetry.emit_reconciliation(closed)
        self._telemetry.emit_book(markout)

    def _cancel_order(self, oid: int) -> HyperliquidOrderAck:
        try:
            acknowledgement = self._adapter.cancel_order(oid)
        except SolCancelTransportError:
            return recovered_cancel_ack(self._recover_oid_status(oid))
        if acknowledgement.accepted:
            return acknowledgement
        return recovered_cancel_ack(self._recover_oid_status(oid))

    def _recover_client_status(self, client_order_id: str) -> HyperliquidOrderStatus:
        lookup = partial(self._adapter.order_status_by_client_id, client_order_id)
        return self._recover_status(lookup, "client order identity")

    def _recover_oid_status(self, oid: int) -> HyperliquidOrderStatus:
        lookup = partial(self._adapter.order_status, oid)
        return self._recover_status(lookup, f"order id {oid}")

    def _recover_status(
        self,
        lookup: Callable[[], HyperliquidOrderStatus],
        identity: str,
    ) -> HyperliquidOrderStatus:
        for attempt in range(_RECOVERY_ATTEMPTS):
            try:
                return lookup()
            except HyperliquidOrderUnavailableError as exc:
                if attempt + 1 == _RECOVERY_ATTEMPTS:
                    raise ApexMMLiveEngineError(
                        f"venue mutation remains ambiguous for {identity}"
                    ) from exc
                self._sleep_fn(_RECOVERY_DELAY_SECONDS)
        raise AssertionError("order recovery exhausted without returning")

    def _emit_funding(self) -> None:
        now_ms = self._timestamp_ms()
        if now_ms < self._next_funding_poll_ms:
            return
        payments = self._adapter.funding_payments(
            start_time_ms=self._funding_cursor_ms,
            end_time_ms=now_ms,
        )
        self._telemetry.emit_funding_payments(payments)
        self._funding_cursor_ms = now_ms + 1
        self._next_funding_poll_ms = now_ms + _FUNDING_POLL_INTERVAL_MS

    def _require_flat_start(
        self,
        preflight: SolVenuePreflight,
        venue: SolReconciliationSnapshot,
    ) -> None:
        if preflight.position.size_signed != 0.0 or not venue.is_flat:
            raise ApexMMLiveEngineError("Apex MM canary requires a flat account start")

    def _validate_position(self, venue: SolReconciliationSnapshot) -> None:
        position = venue.position
        if position.size_signed == 0.0:
            return
        if (
            position.leverage_type != "isolated"
            or position.leverage != self._config.leverage
        ):
            raise ApexMMLiveEngineError(
                "Apex MM inventory must remain isolated at configured leverage"
            )

    def _set_active_state(
        self,
        venue: SolReconciliationSnapshot,
    ) -> ApexMMLiveSnapshot:
        state = (
            ApexMMLiveState.INVENTORY
            if venue.position.size_signed != 0.0
            else ApexMMLiveState.QUOTING
        )
        return self._set_snapshot(
            ApexMMLiveSnapshot(
                state,
                self._snapshot.bid_oid,
                self._snapshot.ask_oid,
                venue.position.size_signed,
                self._snapshot.quote_started_at_ms,
            )
        )

    def _quote_expired(self) -> bool:
        started = self._snapshot.quote_started_at_ms
        age_ms = self._timestamp_ms() - started if started is not None else 0
        return started is None or age_ms >= self._config.quote_refresh_ms

    def _fault(self, message: str) -> ApexMMLiveSnapshot:
        self._telemetry.emit_fault(message)
        fault = ApexMMLiveSnapshot(ApexMMLiveState.FAULT, last_fault=message)
        return self._set_snapshot(fault)

    def _set_snapshot(self, snapshot: ApexMMLiveSnapshot) -> ApexMMLiveSnapshot:
        self._snapshot = snapshot
        self._telemetry.emit_state(snapshot)
        return snapshot

    def _require_running(self, *, allow_fault: bool = False) -> None:
        if not self._started:
            raise ApexMMLiveEngineError("Apex MM live engine is not started")
        if self._snapshot.state is ApexMMLiveState.STOPPED:
            raise ApexMMLiveEngineError("Apex MM live engine is stopped")
        if self._snapshot.state is ApexMMLiveState.FAULT and not allow_fault:
            raise ApexMMLiveEngineError("Apex MM live engine is faulted")

    def _timestamp_ms(self) -> int:
        value = self._now_fn()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ApexMMLiveEngineError("engine clock must be timezone-aware")
        return int(value.timestamp() * 1_000)
