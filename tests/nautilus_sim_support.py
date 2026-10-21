"""Reusable Nautilus strategies and event tapes for simulation tests."""

from __future__ import annotations

import uuid

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.core.data import Data
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model import TraderId
from nautilus_trader.model.data import QuoteTick, TradeTick
from nautilus_trader.model.enums import AggressorSide, OrderSide, OrderType
from nautilus_trader.model.events import (
    OrderAccepted,
    OrderCanceled,
    OrderFilled,
    OrderRejected,
)
from nautilus_trader.model.identifiers import InstrumentId, TradeId
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import LimitOrder
from nautilus_trader.trading.strategy import Strategy

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent
from hypervector.nautilus.bars import synthetic_btc_perp_instrument
from hypervector.nautilus.hl_catalog import convert_hyperliquid_events
from hypervector.nautilus.event_sim import (
    EventSimulationConfig,
    build_event_venue,
)


class RecordingEngine:
    """Capture venue registration arguments without starting Nautilus."""

    def __init__(self) -> None:
        self.arguments: dict[str, object] | None = None

    def add_venue(self, **kwargs: object) -> None:
        """Record one simulated venue registration."""
        self.arguments = kwargs


class CrossingPostOnlyStrategy(Strategy):
    """Submit one post-only order at the opposite best price."""

    def __init__(self, instrument_id: InstrumentId) -> None:
        super().__init__()
        self.instrument_id = instrument_id
        self.submitted = False
        self.rejections: list[OrderRejected] = []
        self.fills: list[OrderFilled] = []

    def on_start(self) -> None:
        self.subscribe_quote_ticks(self.instrument_id)

    def on_quote_tick(self, tick: QuoteTick) -> None:
        if self.submitted:
            return
        order = self.order_factory.limit(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("1.000"),
            price=tick.ask_price,
            post_only=True,
        )
        self.submit_order(order)
        self.submitted = True

    def on_order_rejected(self, event: OrderRejected) -> None:
        self.rejections.append(event)

    def on_order_filled(self, event: OrderFilled) -> None:
        self.fills.append(event)


class AggressiveLimitStrategy(Strategy):
    """Cross two displayed ask levels with one oversized limit order."""

    def __init__(self, instrument_id: InstrumentId) -> None:
        super().__init__()
        self.instrument_id = instrument_id
        self.submitted = False
        self.acceptances: list[OrderAccepted] = []
        self.fills: list[OrderFilled] = []

    def on_start(self) -> None:
        self.subscribe_quote_ticks(self.instrument_id)

    def on_quote_tick(self, tick: QuoteTick) -> None:
        if self.submitted:
            return
        order = self.order_factory.limit(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("7.000"),
            price=Price.from_str("102.0"),
            post_only=False,
        )
        self.submit_order(order)
        self.submitted = True

    def on_order_accepted(self, event: OrderAccepted) -> None:
        self.acceptances.append(event)

    def on_order_filled(self, event: OrderFilled) -> None:
        self.fills.append(event)


class CancelBeforeTradeStrategy(Strategy):
    """Cancel a resting order before a later matching public trade."""

    def __init__(self, instrument_id: InstrumentId) -> None:
        super().__init__()
        self.instrument_id = instrument_id
        self.order: LimitOrder | None = None
        self.cancel_requested_at: int | None = None
        self.acceptances: list[OrderAccepted] = []
        self.cancellations: list[OrderCanceled] = []
        self.fills: list[OrderFilled] = []

    def on_start(self) -> None:
        self.subscribe_quote_ticks(self.instrument_id)

    def on_quote_tick(self, tick: QuoteTick) -> None:
        if self.order is None:
            self.order = self.order_factory.limit(
                instrument_id=self.instrument_id,
                order_side=OrderSide.BUY,
                quantity=Quantity.from_str("2.000"),
                price=Price.from_str("99.0"),
                post_only=True,
            )
            self.submit_order(self.order)
        elif self.acceptances and self.cancel_requested_at is None:
            self.cancel_order(self.order)
            self.cancel_requested_at = tick.ts_event

    def on_order_accepted(self, event: OrderAccepted) -> None:
        self.acceptances.append(event)

    def on_order_canceled(self, event: OrderCanceled) -> None:
        self.cancellations.append(event)

    def on_order_filled(self, event: OrderFilled) -> None:
        self.fills.append(event)


class PartialBracketStrategy(Strategy):
    """Submit an oversized bracket whose entry can only partially fill."""

    def __init__(self, instrument_id: InstrumentId) -> None:
        super().__init__()
        self.instrument_id = instrument_id
        self.submitted = False

    def on_start(self) -> None:
        self.subscribe_quote_ticks(self.instrument_id)

    def on_quote_tick(self, tick: QuoteTick) -> None:
        if self.submitted:
            return
        bracket = self.order_factory.bracket(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("7.000"),
            entry_order_type=OrderType.LIMIT,
            entry_price=Price.from_str("102.0"),
            entry_post_only=False,
            tp_price=Price.from_str("110.0"),
            sl_trigger_price=Price.from_str("90.0"),
        )
        self.submit_order_list(bracket)
        self.submitted = True


def new_engine() -> BacktestEngine:
    """Create an isolated engine identity for one deterministic scenario."""
    suffix = uuid.uuid4().hex[:8].upper()
    return BacktestEngine(
        BacktestEngineConfig(
            trader_id=TraderId(f"HV-SIM-{suffix}"),
            instance_id=UUID4(),
            logging=LoggingConfig(bypass_logging=True),
        )
    )


def partial_fill_signature() -> tuple[tuple[float, float, float], ...]:
    """Run the split-depth scenario and return stable semantic fill fields."""
    engine = new_engine()
    instrument = synthetic_btc_perp_instrument()
    strategy = AggressiveLimitStrategy(instrument.id)
    try:
        build_event_venue(
            engine,
            init_cash=10_000.0,
            config=EventSimulationConfig(
                submit_latency_ms=0,
                cancel_latency_ms=0,
                random_seed=11,
            ),
        )
        engine.add_instrument(instrument)
        engine.add_data(market_data(instrument.id, split_asks=True))
        engine.add_strategy(strategy)
        engine.run()
        return tuple(
            (
                fill.last_px.as_double(),
                fill.last_qty.as_double(),
                fill.commission.as_double(),
            )
            for fill in strategy.fills
        )
    finally:
        engine.dispose()


def market_data(
    instrument_id: InstrumentId,
    *,
    split_asks: bool = False,
    deeper_bid: bool = False,
) -> list[Data]:
    """Build a complete L2 snapshot followed by quote-clock events."""
    asks = _ask_levels(split_asks)
    bids = _bid_levels(deeper_bid)
    snapshot = L2SnapshotEvent(
        symbol="BTC",
        exchange_ts_ms=1_000,
        received_ts_ns=1_000_000_000,
        bids=bids,
        asks=asks,
    )
    converted = convert_hyperliquid_events(
        l2_events=(snapshot,),
        trade_events=(),
        instrument_id=str(instrument_id),
        price_precision=1,
        size_precision=3,
    )
    return [*converted.book_deltas, *_quotes(instrument_id)]


def cancel_tape(instrument_id: InstrumentId) -> list[Data]:
    """Return dense clock events, then a trade after cancellation can finish."""
    data = [
        item
        for item in market_data(instrument_id, deeper_bid=True)
        if not isinstance(item, QuoteTick)
    ]
    data.extend(
        quote(instrument_id, timestamp=timestamp)
        for timestamp in range(1_000_000_000, 1_310_000_000, 10_000_000)
    )
    data.extend(
        [
            TradeTick(
                instrument_id=instrument_id,
                price=Price.from_str("99.0"),
                size=Quantity.from_str("10.000"),
                aggressor_side=AggressorSide.SELLER,
                trade_id=TradeId("cancel-test-trade"),
                ts_event=1_500_000_000,
                ts_init=1_500_000_000,
            ),
            quote(instrument_id, timestamp=1_600_000_000),
        ]
    )
    return data


def quote(instrument_id: InstrumentId, *, timestamp: int) -> QuoteTick:
    """Return one top-of-book clock event."""
    return QuoteTick(
        instrument_id=instrument_id,
        bid_price=Price.from_str("100.0"),
        ask_price=Price.from_str("101.0"),
        bid_size=Quantity.from_str("5.000"),
        ask_size=Quantity.from_str("5.000"),
        ts_event=timestamp,
        ts_init=timestamp,
    )


def _quotes(instrument_id: InstrumentId) -> list[QuoteTick]:
    return [
        quote(instrument_id, timestamp=timestamp)
        for timestamp in (1_000_000_000, 2_000_000_000, 3_000_000_000)
    ]


def _ask_levels(split: bool) -> tuple[BookLevel, ...]:
    if split:
        return (
            BookLevel(price=101.0, size=2.0, order_count=1),
            BookLevel(price=102.0, size=3.0, order_count=1),
        )
    return (BookLevel(price=101.0, size=5.0, order_count=1),)


def _bid_levels(deeper: bool) -> tuple[BookLevel, ...]:
    if deeper:
        return (
            BookLevel(price=100.0, size=5.0, order_count=1),
            BookLevel(price=99.0, size=1.0, order_count=1),
        )
    return (BookLevel(price=100.0, size=5.0, order_count=1),)
