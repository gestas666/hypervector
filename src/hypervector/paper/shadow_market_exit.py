"""Immediate fresh-BBO taker exits for event-driven shadow execution."""

from __future__ import annotations

from hypervector.data.hl_events import L2SnapshotEvent
from hypervector.execution import OrderCommand, VenueOrderEvent
from hypervector.nautilus.event_sim import EventSimulationConfig
from hypervector.paper.shadow_execution_models import (
    EXECUTION_MODEL,
    MARGIN_MODEL,
    ShadowExecutionRecord,
    ShadowOrder,
    timestamp_ms,
)


class ShadowMarketExitMixin:
    """Execute one full reduce-only market exit from fresh public BBO evidence."""

    _symbol: str
    _position_quantity: float
    _latest_book: L2SnapshotEvent | None
    _evidence_fresh: bool
    _max_event_age_ms: int
    _taker_fee_rate: float
    _orders: dict[str, ShadowOrder]
    _records: list[ShadowExecutionRecord]
    _config: EventSimulationConfig
    _last_observed_at: str
    _last_source: str | None

    def execute_market(
        self,
        command: OrderCommand,
        *,
        observed_at: str,
    ) -> tuple[tuple[VenueOrderEvent, ...], ShadowExecutionRecord]:
        """Fill a maximum-hold exit at current BBO or fail closed."""
        book, freshness = self._validated_exit_book(command, observed_at)
        price = book.bids[0].price if command.side == "sell" else book.asks[0].price
        fee = command.quantity * price * self._taker_fee_rate
        canceled = self._retire_reduce_orders(observed_at)
        self._apply_fill(command, command.quantity, price, fee)
        fill = VenueOrderEvent(
            client_order_id=command.client_order_id,
            venue_order_id=f"shadow-{command.client_order_id}",
            event_type="filled",
            event_at=observed_at,
            last_quantity=command.quantity,
            cumulative_quantity=command.quantity,
            fill_price=price,
            fee_usd=fee,
            liquidity_side="taker",
            reason="maximum_hold_exit",
        )
        record = self._market_exit_record(fill, book, freshness)
        self._records.append(record)
        self._last_observed_at = observed_at
        self._last_source = book.source
        return canceled + (fill,), record

    def _validated_exit_book(
        self,
        command: OrderCommand,
        observed_at: str,
    ) -> tuple[L2SnapshotEvent, float]:
        if command.symbol != self._symbol:
            raise ValueError(f"command symbol {command.symbol!r} != {self._symbol!r}")
        if command.order_type != "market" or command.order_role != "exit":
            raise ValueError(
                "immediate shadow execution requires a market exit command"
            )
        if command.submitted_at != observed_at:
            raise ValueError("market exit submitted_at must equal observed_at")
        if abs(command.quantity - abs(self._position_quantity)) > 1e-12:
            raise ValueError("market exit quantity must equal the open position")
        expected_side = "sell" if self._position_quantity > 0.0 else "buy"
        if self._position_quantity == 0.0 or command.side != expected_side:
            raise ValueError("market exit side must reduce the open position")
        book = self._latest_book
        if book is None or not self._evidence_fresh:
            raise RuntimeError("maximum-hold exit requires fresh BBO evidence")
        freshness = timestamp_ms(observed_at) - book.exchange_ts_ms
        if freshness < 0 or freshness > self._max_event_age_ms:
            raise RuntimeError("maximum-hold exit BBO evidence is stale")
        return book, float(freshness)

    def _retire_reduce_orders(self, observed_at: str) -> tuple[VenueOrderEvent, ...]:
        events: list[VenueOrderEvent] = []
        for order in self._orders.values():
            if order.status == "terminal" or not order.command.reduce_only:
                continue
            order.status = "terminal"
            events.append(
                VenueOrderEvent(
                    client_order_id=order.command.client_order_id,
                    venue_order_id=f"shadow-{order.command.client_order_id}",
                    event_type="canceled",
                    event_at=observed_at,
                    last_quantity=0.0,
                    cumulative_quantity=order.cumulative_quantity,
                    fill_price=None,
                    fee_usd=0.0,
                    liquidity_side=None,
                    reason="maximum_hold_exit",
                )
            )
        return tuple(events)

    def _market_exit_record(
        self,
        event: VenueOrderEvent,
        book: L2SnapshotEvent,
        freshness: float,
    ) -> ShadowExecutionRecord:
        return ShadowExecutionRecord(
            event=event,
            execution_model=EXECUTION_MODEL,
            data_source=book.source,
            evidence_fresh=True,
            event_freshness_ms=freshness,
            configured_latency_ms=self._config.submit_latency_ms,
            queue_ahead_quantity=0.0,
            requested_quantity=event.last_quantity,
            cumulative_filled_quantity=event.cumulative_quantity,
            remaining_quantity=0.0,
            liquidity_side="taker",
            margin_model=MARGIN_MODEL,
        )

    def _apply_fill(
        self,
        command: OrderCommand,
        quantity: float,
        price: float,
        fee: float,
    ) -> None:
        raise NotImplementedError
