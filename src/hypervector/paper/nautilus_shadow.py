"""Event-driven Hypervelocity shadow port with Nautilus-aligned friction."""

from __future__ import annotations

from datetime import UTC, datetime

from hypervector.data.hl_events import L2SnapshotEvent, PublicTradeEvent, StreamGap
from hypervector.execution import AccountSnapshot, OrderCommand, VenueOrderEvent
from hypervector.nautilus.hyperliquid_margin import IsolatedMarginPosition
from hypervector.nautilus.hypervelocity_sim import HypervelocitySimulationConfig
from hypervector.paper.shadow_execution_models import (
    EXECUTION_MODEL,
    MARGIN_MODEL,
    ShadowExecutionRecord,
    ShadowLiquidation,
    ShadowOrder,
    ShadowOrderTelemetry,
    fill_event,
    finite,
    iso_ms,
    iso_ns,
    known_open_order,
    matching_orders,
    nonempty,
    order_telemetry,
    positive,
    positive_rate,
    queue_ahead,
    rate,
    shadow_marked_equity,
    state_event,
    timestamp_ms,
    would_cross,
)
from hypervector.paper.shadow_liquidation import ShadowLiquidationMixin
from hypervector.paper.shadow_market_exit import ShadowMarketExitMixin
from hypervector.paper.shadow_restore import ShadowRestoreMixin

_TRADE_DEDUP_CAPACITY = 10_000


class NautilusShadowExecutionPort(
    ShadowMarketExitMixin,
    ShadowLiquidationMixin,
    ShadowRestoreMixin,
):
    """Consume normalized events with explicit Nautilus-aligned friction state."""

    def __init__(
        self,
        *,
        symbol: str,
        initial_cash_usd: float,
        simulation_config: HypervelocitySimulationConfig,
        maker_fee_rate: float,
        taker_fee_rate: float,
        leverage: float,
        maintenance_rate: float,
        max_event_age_ms: int,
    ) -> None:
        nonempty(symbol, "symbol")
        positive(initial_cash_usd, "initial_cash_usd")
        rate(maker_fee_rate, "maker_fee_rate")
        rate(taker_fee_rate, "taker_fee_rate")
        positive(leverage, "leverage")
        positive_rate(maintenance_rate, "maintenance_rate")
        if max_event_age_ms <= 0:
            raise ValueError("max_event_age_ms must be positive")
        self._symbol = symbol
        self._initial_cash = initial_cash_usd
        self._realized_equity = initial_cash_usd
        self._config = simulation_config
        self._maker_fee_rate = maker_fee_rate
        self._taker_fee_rate = taker_fee_rate
        self._leverage = leverage
        self._maintenance_rate = maintenance_rate
        self._max_event_age_ms = max_event_age_ms
        self._orders: dict[str, ShadowOrder] = {}
        self._events: list[VenueOrderEvent] = []
        self._records: list[ShadowExecutionRecord] = []
        self._annotations: list[str] = []
        self._seen_trade_keys: dict[str, None] = {}
        self._latest_book: L2SnapshotEvent | None = None
        self._gap_until_ms: int | None = None
        self._evidence_fresh = False
        self._last_observed_at = datetime.now(tz=UTC).isoformat()
        self._last_source: str | None = None
        self._position_quantity = 0.0
        self._position_average_price: float | None = None
        self._position_fees = 0.0
        self._funding_net = 0.0
        self._last_mark: float | None = None
        self._last_liquidation: ShadowLiquidation | None = None
        self._liquidation_cooldown_until_ms: int | None = None

    def submit(self, command: OrderCommand) -> VenueOrderEvent:
        """Schedule a command and return an immediate submitted event."""
        if command.symbol != self._symbol:
            raise ValueError(f"command symbol {command.symbol!r} != {self._symbol!r}")
        if command.client_order_id in self._orders:
            raise ValueError(f"duplicate client_order_id {command.client_order_id!r}")
        submitted_ms = timestamp_ms(command.submitted_at)
        self._orders[command.client_order_id] = ShadowOrder(
            command=command,
            activation_ms=submitted_ms + self._config.submit_latency_ms,
        )
        return state_event(command.client_order_id, "submitted", command.submitted_at)

    def cancel(self, client_order_id: str, *, requested_at: str) -> VenueOrderEvent:
        """Schedule cancellation while allowing fills during cancel latency."""
        order = known_open_order(self._orders, client_order_id)
        if order.cancel_effective_ms is not None:
            raise ValueError(f"cancel already pending for {client_order_id!r}")
        order.cancel_effective_ms = (
            timestamp_ms(requested_at) + self._config.cancel_latency_ms
        )
        order.status = "cancel_pending"
        return state_event(client_order_id, "cancel_pending", requested_at)

    def reconcile(self) -> tuple[VenueOrderEvent, ...]:
        """Drain normalized venue events created while ingesting public data."""
        events = tuple(self._events)
        self._events.clear()
        return events

    def account_snapshot(self) -> AccountSnapshot:
        """Return current mark-to-market isolated shadow account state."""
        equity = max(0.0, self._marked_equity())
        margin = self.position_margin_usd
        return AccountSnapshot(
            observed_at=self._last_observed_at,
            equity_usd=equity,
            available_balance_usd=max(0.0, equity - margin),
            position_quantity=self._position_quantity,
            position_average_price=self._position_average_price,
            margin_mode="isolated",
            leverage=self._leverage,
            maker_fee_rate=self._maker_fee_rate,
            taker_fee_rate=self._taker_fee_rate,
        )

    def ingest(self, event: L2SnapshotEvent | PublicTradeEvent | StreamGap) -> None:
        """Advance the simulated venue from one normalized public event."""
        if event.symbol != self._symbol:
            raise ValueError(f"event symbol {event.symbol!r} != {self._symbol!r}")
        if isinstance(event, StreamGap):
            self._declare_gap(event)
            return
        self._last_observed_at = iso_ms(event.exchange_ts_ms)
        self._last_source = event.source
        self._process_effective_cancels(event.exchange_ts_ms)
        if isinstance(event, L2SnapshotEvent):
            self._ingest_book(event)
            self._activate_orders(event.exchange_ts_ms)
            return
        if event.trade_key in self._seen_trade_keys:
            return
        self._seen_trade_keys[event.trade_key] = None
        if len(self._seen_trade_keys) > _TRADE_DEDUP_CAPACITY:
            self._seen_trade_keys.pop(next(iter(self._seen_trade_keys)))
        self._activate_orders(event.exchange_ts_ms)
        self._ingest_trade(event)

    def order_telemetry(self, client_order_id: str) -> ShadowOrderTelemetry:
        """Return current per-order execution evidence."""
        order = self._orders.get(client_order_id)
        if order is None:
            raise KeyError(client_order_id)
        return order_telemetry(
            order,
            source=self._last_source,
            evidence_fresh=self._evidence_fresh,
            submit_latency_ms=self._config.submit_latency_ms,
            cancel_latency_ms=self._config.cancel_latency_ms,
        )

    def execution_records(self) -> tuple[ShadowExecutionRecord, ...]:
        """Return immutable fill evidence without draining it."""
        return tuple(self._records)

    def execution_annotations(self) -> tuple[str, ...]:
        """Return technical evidence annotations without strategy implications."""
        return tuple(self._annotations)

    @property
    def position_margin_usd(self) -> float:
        """Return margin assigned only to the current isolated position."""
        if self._position_average_price is None:
            return 0.0
        return (
            abs(self._position_quantity) * self._position_average_price / self._leverage
        )

    @property
    def funding_net_usd(self) -> float:
        """Return signed funding for the current position; positive means received."""
        return self._funding_net

    @property
    def liquidation_price(self) -> float | None:
        """Return the current official-form isolated maintenance boundary."""
        position = self._margin_position()
        return position.liquidation_price() if position is not None else None

    @property
    def last_liquidation(self) -> ShadowLiquidation | None:
        """Return the latest isolated liquidation record, if any."""
        return self._last_liquidation

    @property
    def liquidation_cooldown_until_ms(self) -> int | None:
        """Return the restored or live partial-liquidation cooldown boundary."""
        return self._liquidation_cooldown_until_ms

    def apply_funding(
        self,
        *,
        hourly_rate: float,
        mark_price: float,
        applied_at: str,
    ) -> float:
        """Apply one signed hourly funding transfer to the open position."""
        finite(hourly_rate, "hourly_rate")
        positive(mark_price, "mark_price")
        timestamp_ms(applied_at)
        if self._position_quantity == 0.0:
            return 0.0
        paid_by_long = abs(self._position_quantity) * mark_price * hourly_rate
        funding = -paid_by_long if self._position_quantity > 0.0 else paid_by_long
        self._funding_net += funding
        self._realized_equity += funding
        self._last_mark = mark_price
        self._last_observed_at = applied_at
        return funding

    def _ingest_book(self, event: L2SnapshotEvent) -> None:
        self._latest_book = event
        lag_ms = event.received_ts_ns / 1_000_000 - event.exchange_ts_ms
        gap_closed = self._gap_until_ms is None or (
            event.exchange_ts_ms >= self._gap_until_ms
        )
        self._evidence_fresh = lag_ms <= self._max_event_age_ms and gap_closed
        if gap_closed:
            self._gap_until_ms = None
        midpoint = (event.bids[0].price + event.asks[0].price) / 2.0
        self._last_mark = midpoint

    def _ingest_trade(self, event: PublicTradeEvent) -> None:
        book = self._latest_book
        if book is None or not self._evidence_fresh:
            self._annotate_uncertain()
            return
        freshness = event.exchange_ts_ms - book.exchange_ts_ms
        if freshness < 0 or freshness > self._max_event_age_ms:
            self._evidence_fresh = False
            self._annotate_uncertain()
            return
        receipt_lag = event.received_ts_ns / 1_000_000 - event.exchange_ts_ms
        if receipt_lag < 0 or receipt_lag > self._max_event_age_ms:
            self._evidence_fresh = False
            self._annotate_uncertain()
            return
        freshness = max(freshness, receipt_lag)
        self._last_mark = event.price
        available = event.size
        for order in matching_orders(self._orders, event):
            available = self._consume_trade(order, event, available, freshness)
            if available <= 1e-12:
                break

    def _activate_orders(self, exchange_ms: int) -> None:
        book = self._latest_book
        if book is None or not self._evidence_fresh:
            return
        book_age = exchange_ms - book.exchange_ts_ms
        if book_age < 0 or book_age > self._max_event_age_ms:
            self._evidence_fresh = False
            return
        for order in self._orders.values():
            if order.activated or order.status == "terminal":
                continue
            if order.activation_ms > exchange_ms:
                continue
            if would_cross(order.command, book):
                order.status = "terminal"
                self._events.append(
                    state_event(
                        order.command.client_order_id,
                        "rejected",
                        iso_ms(exchange_ms),
                        reason="post_only_would_cross",
                    )
                )
                continue
            order.activated = True
            order.status = (
                "cancel_pending" if order.cancel_effective_ms is not None else "active"
            )
            order.queue_ahead_quantity = self._queue_ahead(order)
            self._events.append(
                state_event(
                    order.command.client_order_id,
                    "accepted",
                    iso_ms(exchange_ms),
                )
            )

    def _process_effective_cancels(self, exchange_ms: int) -> None:
        for order in self._orders.values():
            effective = order.cancel_effective_ms
            if (
                order.status == "terminal"
                or effective is None
                or effective > exchange_ms
            ):
                continue
            order.status = "terminal"
            self._events.append(
                state_event(
                    order.command.client_order_id,
                    "canceled",
                    iso_ms(exchange_ms),
                    cumulative=order.cumulative_quantity,
                )
            )

    def _consume_trade(
        self,
        order: ShadowOrder,
        trade: PublicTradeEvent,
        available: float,
        freshness_ms: float,
    ) -> float:
        queued = min(order.queue_ahead_quantity, available)
        order.queue_ahead_quantity -= queued
        available -= queued
        fill_quantity = min(order.remaining_quantity, available)
        if fill_quantity <= 1e-12:
            return available
        order.cumulative_quantity += fill_quantity
        available -= fill_quantity
        final = order.remaining_quantity <= 1e-12
        order.status = "terminal" if final else order.status
        execution_price = order.command.limit_price or trade.price
        fee = fill_quantity * execution_price * self._maker_fee_rate
        self._apply_fill(order.command, fill_quantity, execution_price, fee)
        event = fill_event(order, trade, fill_quantity, fee, final)
        self._events.append(event)
        self._records.append(
            ShadowExecutionRecord(
                event=event,
                execution_model=EXECUTION_MODEL,
                data_source=trade.source,
                evidence_fresh=True,
                event_freshness_ms=freshness_ms,
                configured_latency_ms=self._config.submit_latency_ms,
                queue_ahead_quantity=order.queue_ahead_quantity,
                requested_quantity=order.command.quantity,
                cumulative_filled_quantity=order.cumulative_quantity,
                remaining_quantity=order.remaining_quantity,
                liquidity_side="maker",
                margin_model=MARGIN_MODEL,
            )
        )
        return available

    def _apply_fill(
        self,
        command: OrderCommand,
        quantity: float,
        price: float,
        fee: float,
    ) -> None:
        self._realized_equity -= fee
        signed = quantity if command.side == "buy" else -quantity
        if command.order_role == "entry":
            self._position_fees += fee
            self._increase_position(signed, price)
            return
        self._reduce_position(signed, price)

    def _increase_position(self, signed: float, price: float) -> None:
        if self._position_quantity != 0.0 and self._position_quantity * signed < 0.0:
            raise ValueError("entry fill would reverse an open position")
        old_notional = abs(self._position_quantity) * (
            self._position_average_price or 0.0
        )
        new_quantity = self._position_quantity + signed
        average = (old_notional + abs(signed) * price) / abs(new_quantity)
        self._position_quantity = new_quantity
        self._position_average_price = average

    def _reduce_position(self, signed: float, price: float) -> None:
        if self._position_quantity == 0.0 or self._position_quantity * signed >= 0.0:
            raise ValueError("target fill must reduce an open position")
        if abs(signed) > abs(self._position_quantity) + 1e-12:
            raise ValueError("target fill exceeds open position")
        before_quantity = abs(self._position_quantity)
        side = 1.0 if self._position_quantity > 0.0 else -1.0
        entry = self._position_average_price
        if entry is None:
            raise ValueError("open position requires average price")
        self._realized_equity += side * abs(signed) * (price - entry)
        self._position_quantity += signed
        if abs(self._position_quantity) <= 1e-12:
            self._clear_position()
            return
        self._scale_open_cost_basis(
            before_quantity=before_quantity,
            remaining_quantity=abs(self._position_quantity),
        )

    def _scale_open_cost_basis(
        self,
        *,
        before_quantity: float,
        remaining_quantity: float,
    ) -> None:
        """Retain only fee and funding basis attributable to open quantity."""
        if before_quantity <= 0.0:
            raise ValueError("cost-basis reduction requires an open position")
        if not 0.0 <= remaining_quantity <= before_quantity:
            raise ValueError("remaining quantity must not exceed prior quantity")
        retained_fraction = remaining_quantity / before_quantity
        self._position_fees *= retained_fraction
        self._funding_net *= retained_fraction

    def _clear_position(self) -> None:
        self._position_quantity = 0.0
        self._position_average_price = None
        self._position_fees = 0.0
        self._funding_net = 0.0

    def _margin_position(self) -> IsolatedMarginPosition | None:
        if self._position_quantity == 0.0 or self._position_average_price is None:
            return None
        return IsolatedMarginPosition(
            symbol=self._symbol,
            side="long" if self._position_quantity > 0.0 else "short",
            quantity=abs(self._position_quantity),
            entry_price=self._position_average_price,
            isolated_margin=self.position_margin_usd,
            maintenance_rate=self._maintenance_rate,
            fees_paid_usd=self._position_fees,
            funding_net_usd=self._funding_net,
        )

    def _queue_ahead(self, order: ShadowOrder) -> float:
        book = self._latest_book
        if book is None:
            return 0.0
        return queue_ahead(order, book, tuple(self._orders.values()))

    def _declare_gap(self, gap: StreamGap) -> None:
        self._evidence_fresh = False
        self._gap_until_ms = gap.next_exchange_ts_ms
        self._last_observed_at = iso_ns(gap.detected_ts_ns)
        self._last_source = f"gap:{gap.channel}"
        self._annotate_uncertain()

    def _annotate_uncertain(self) -> None:
        if (
            not self._annotations
            or self._annotations[-1] != "execution_evidence_uncertain"
        ):
            self._annotations.append("execution_evidence_uncertain")

    def _marked_equity(self) -> float:
        return shadow_marked_equity(
            self._realized_equity,
            self._position_quantity,
            self._position_average_price,
            self._last_mark,
        )
