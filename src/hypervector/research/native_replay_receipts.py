"""Explicit request and receipt clocks for isolated recorded IOC experiments."""

from dataclasses import dataclass
from decimal import Decimal

from hypervector.research.native_replay_depth import IocMatch, RecordedBook
from hypervector.research.native_replay_events import FillEvent, require_amount, require_clock, require_name


@dataclass(frozen=True)
class IocOrder:
    """Already-rounded submitted quantity/limit, with a declared signed fee model."""

    client_order_id: str
    symbol: str
    side: str
    quantity: Decimal
    limit_price: Decimal
    leverage: Decimal
    fee_rate: Decimal
    decision_time_ms: int
    dispatch_time_ms: int
    arrival_time_ms: int
    reduce_only: bool

    def __post_init__(self) -> None:
        """Validate the request without inferring transport delay or exchange fees."""
        require_name(self.client_order_id, "IOC client order ID")
        require_name(self.symbol, "IOC symbol")
        if self.side not in ("buy", "sell") or type(self.reduce_only) is not bool:
            raise ValueError("IOC requires buy/sell and an explicit reduce_only bool")
        for name in ("quantity", "limit_price", "leverage"):
            require_amount(getattr(self, name), name, positive=True)
        require_amount(self.fee_rate, "fee rate")
        clocks = (self.decision_time_ms, self.dispatch_time_ms, self.arrival_time_ms)
        for value in clocks:
            require_clock(value, "IOC request clock")
        if not clocks[0] <= clocks[1] <= clocks[2]:
            raise ValueError("IOC clocks require decision <= dispatch <= arrival")


@dataclass(frozen=True)
class ReceiptTiming:
    """Declared visibility/response clocks; these are inputs, not measured latency."""

    fill_visible_ms: int
    order_visible_ms: int
    response_ms: int
    response_lost: bool

    def __post_init__(self) -> None:
        """Require exact clocks and an explicit transport response-loss scenario."""
        for clock in (self.fill_visible_ms, self.order_visible_ms, self.response_ms):
            require_clock(clock, "IOC receipt time")
        if type(self.response_lost) is not bool:
            raise ValueError("response_lost must be an explicit bool")


@dataclass
class AcceptedIoc:
    """Internal scheduled execution, including its original immutable evidence."""

    oid: int
    order: IocOrder
    book: RecordedBook
    timing: ReceiptTiming
    maximum_book_delay_ms: int
    match: IocMatch
    applied: bool = False
    fills: tuple[FillEvent, ...] = ()
