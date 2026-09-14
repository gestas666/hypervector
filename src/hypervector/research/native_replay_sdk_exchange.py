"""Native SDK-shaped mutations backed solely by the local replay account and books."""

from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING

from hyperliquid.exchange import Exchange
from hyperliquid.utils.types import Cloid

from hypervector.live.hyperliquid_sol_parsing import mapping
from hypervector.research.native_replay_events import require_amount
from hypervector.research.native_replay_receipts import IocOrder, ReceiptTiming
from hypervector.research.native_replay_sdk_models import ReplayOrderRecord

if TYPE_CHECKING:
    from hypervector.research.native_replay_sdk import ReplaySdk


class ReplaySdkExchange:
    """Implement declared market/protective actions without a signer or exchange client."""

    def __init__(self, replay: "ReplaySdk") -> None:
        """Use only offline source/account objects; the SDK class supplies pure price arithmetic."""
        self.replay, self.info = replay, replay.info

    def update_leverage(self, leverage: int, name: str, is_cross: bool = True) -> object:
        """Set an explicit isolated leverage scenario for a flat configured market."""
        market = self.replay.markets[name].metadata
        if is_cross or type(leverage) is not int or not 0 < leverage <= market.max_leverage:
            raise ValueError("replay requires isolated leverage within the declared venue maximum")
        if name in self.replay.account.snapshot().positions:
            raise ValueError(
                "replay leverage changes with open exposure require a separate scenario"
            )
        self.replay.leverage[name] = leverage
        return {"status": "ok"}

    def market_open(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        px: float | None = None,
        slippage: float = 0.05,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        """Use the native submitted lot quantity and SDK limit arithmetic at modeled arrival."""
        return self._ioc(name, is_buy, sz, px, slippage, cloid, builder, False)

    def market_close(
        self,
        coin: str,
        sz: float | None = None,
        px: float | None = None,
        slippage: float = 0.05,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        """Reduce only the explicitly requested quantity of reconciled modeled exposure."""
        self.replay.advance_to(self.replay.clock.now_ms)
        position = self.replay.account.snapshot().positions.get(coin)
        if position is None or sz is None:
            raise ValueError("replay market close requires open exposure and an explicit quantity")
        return self._ioc(coin, position.quantity_signed < 0, sz, px, slippage, cloid, builder, True)

    def _ioc(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        px: float | None,
        slippage: float,
        cloid: object | None,
        builder: object | None,
        reduce_only: bool,
    ) -> object:
        identity = self._identity(cloid, builder)
        if px is None or type(is_buy) is not bool:
            raise ValueError("replay IOC needs an explicit reference price and side")
        require_amount(Decimal(str(px)), "IOC reference price", positive=True)
        quantity = Decimal(str(sz))
        market, delay = self.replay.markets[name], self.replay.timing
        if name not in self.replay.leverage:
            raise ValueError(f"isolated replay leverage was not configured for {name}")
        limit = Decimal(str(Exchange._slippage_price(self, name, is_buy, slippage, px)))
        dispatch = self.replay.clock.now_ms
        arrival = dispatch + delay.arrival_delay_ms
        step = Decimal(1).scaleb(-market.metadata.size_decimals)
        book = self.replay.execution_book(name, arrival, step)
        order = IocOrder(
            identity,
            name,
            "buy" if is_buy else "sell",
            quantity,
            limit,
            Decimal(self.replay.leverage[name]),
            market.taker_rate,
            self.replay.decision_time(name, reduce_only),
            dispatch,
            arrival,
            reduce_only,
        )
        receipt = ReceiptTiming(
            book.exchange_time_ms + delay.fill_visible_delay_ms,
            book.exchange_time_ms + delay.order_visible_delay_ms,
            book.exchange_time_ms + delay.response_delay_ms,
            identity in self.replay.response_losses,
        )
        return self.replay.submit_ioc(order, book, receipt)

    def order(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        order_type: object,
        reduce_only: bool = False,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        """Accept an explicit reduce-only stop or post-only target; no queue fill is inferred."""
        identity = self._identity(cloid, builder)
        if type(is_buy) is not bool or reduce_only is not True:
            raise ValueError("resting replay orders require a reduce-only protective side")
        quantity, limit = Decimal(str(sz)), Decimal(str(limit_px))
        self._validate_protection(name, is_buy, quantity, limit)
        trigger = self._trigger(order_type)
        if trigger is None:
            if self._marketable_target(name, is_buy, limit):
                return self._ack({"error": "Post-only order would have immediately matched."})
        else:
            self.replay.advance_to(self.replay.clock.now_ms + self.replay.timing.arrival_delay_ms)
        self._validate_protection(name, is_buy, quantity, limit)
        return self._accept_protection(identity, name, is_buy, quantity, limit, trigger)

    def _validate_protection(
        self, name: str, is_buy: bool, quantity: Decimal, limit: Decimal
    ) -> None:
        position = self.replay.account.snapshot().positions.get(name)
        if position is None or (position.quantity_signed < 0) != is_buy:
            raise ValueError("protective replay order must oppose existing exposure")
        require_amount(quantity, "protective quantity", positive=True)
        require_amount(limit, "protective limit", positive=True)
        step = Decimal(1).scaleb(-self.replay.markets[name].metadata.size_decimals)
        if quantity % step or quantity > abs(position.quantity_signed):
            raise ValueError(
                "protective replay quantity must be lot-aligned and bounded by exposure"
            )

    def _accept_protection(
        self,
        identity: str,
        name: str,
        is_buy: bool,
        quantity: Decimal,
        limit: Decimal,
        trigger: Decimal | None,
    ) -> object:
        now, timing = self.replay.clock.now_ms, self.replay.timing
        oid = self.replay.next_oid()
        self.replay.orders[oid] = ReplayOrderRecord(
            oid,
            identity,
            name,
            is_buy,
            quantity,
            quantity,
            limit,
            trigger,
            True,
            True,
            now,
            now + timing.order_visible_delay_ms,
            "open",
            now,
            now + timing.order_visible_delay_ms,
        )
        self.replay.advance_to(now + timing.mutation_response_ms)
        return self._ack({"resting": {"oid": oid}})

    def _marketable_target(self, name: str, is_buy: bool, limit: Decimal) -> bool:
        arrival = self.replay.clock.now_ms + self.replay.timing.arrival_delay_ms
        step = Decimal(1).scaleb(-self.replay.markets[name].metadata.size_decimals)
        book = self.replay.execution_book(name, arrival, step)
        if (
            book.symbol != name
            or not 0 <= book.exchange_time_ms - arrival <= self.replay.maximum_book_delay_ms
        ):
            raise ValueError(
                "post-only replay needs a matching book within its declared arrival window"
            )
        self.replay.advance_to(book.exchange_time_ms)
        return limit >= book.asks[0].price if is_buy else limit <= book.bids[0].price

    def cancel(self, name: str, oid: int) -> object:
        """Cancel one exact owned open order while preserving delayed terminal visibility."""
        self.replay.advance_to(self.replay.clock.now_ms + self.replay.timing.arrival_delay_ms)
        row = self.replay.orders.get(oid)
        if row is None or row.symbol != name or not row.resting or row.status != "open":
            return self._ack({"error": "Order was never placed, already canceled, or filled."})
        now, timing = self.replay.clock.now_ms, self.replay.timing
        self.replay.orders[oid] = replace(
            row,
            previous=row,
            status="canceled",
            status_ms=now,
            changed_visible_ms=now + timing.order_visible_delay_ms,
        )
        self.replay.advance_to(now + timing.mutation_response_ms)
        return self._ack("success")

    def bulk_orders(
        self, order_requests: list[object], builder: object | None = None, grouping: str = "na"
    ) -> object:
        """Reject unsupported batch semantics instead of fabricating multi-order execution."""
        raise ValueError(
            "bulk opening/post-only replay requires a separately specified queue model"
        )

    def _identity(self, cloid: object | None, builder: object | None) -> str:
        if builder is not None or not isinstance(cloid, Cloid):
            raise ValueError("offline replay requires a native Cloid and no unmodeled builder fee")
        identity = cloid.to_raw()
        if any(row.client_id == identity for row in self.replay.orders.values()):
            raise ValueError("replay SDK client order identity was already submitted")
        return identity

    @staticmethod
    def _trigger(order_type: object) -> Decimal | None:
        body = mapping(order_type, "replay order type")
        if body == {"limit": {"tif": "Alo"}}:
            return None
        trigger = mapping(body.get("trigger"), "replay trigger")
        if trigger.get("isMarket") is not True or trigger.get("tpsl") != "sl":
            raise ValueError("replay supports explicit stop-market triggers and post-only targets")
        price = Decimal(str(trigger.get("triggerPx")))
        require_amount(price, "stop trigger", positive=True)
        return price

    @staticmethod
    def _ack(status: object) -> dict[str, object]:
        return {"status": "ok", "response": {"type": "order", "data": {"statuses": [status]}}}
