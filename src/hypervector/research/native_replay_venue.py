"""Stateful offline IOC execution with separate economics and receipt visibility.

Only IOC execution is implemented here. Stops, resting targets, collateral
transfers, liquidation, rate limits and a complete SDK port remain separate
integration work. Recorded snapshot liquidity and timing are declared scenarios.
"""

from decimal import localcontext

from requests import RequestException

from hypervector.research.native_replay_account import ExactFillAccount, REPLAY_DECIMAL_PRECISION
from hypervector.research.native_replay_clock import ReplayClock
from hypervector.research.native_replay_depth import BookLiquidity, RecordedBook
from hypervector.research.native_replay_events import FillEvent, require_clock
from hypervector.research.native_replay_receipts import AcceptedIoc, IocOrder, ReceiptTiming

__all__ = ["IocOrder", "ReceiptTiming", "RecordedIocVenue"]


class RecordedIocVenue:
    """Drive exact shared economics without constructing an SDK client or signer."""

    def __init__(self, account: ExactFillAccount, clock: ReplayClock) -> None:
        """Use explicit account/clock ownership and no live configuration or I/O."""
        self.account, self.clock = account, clock
        self._orders: dict[str, AcceptedIoc] = {}
        self._books: dict[str, BookLiquidity] = {}
        self._latest_book: dict[str, int] = {}

    def submit(
        self,
        order: IocOrder,
        book: RecordedBook,
        timing: ReceiptTiming,
        *,
        maximum_book_delay_ms: int,
    ) -> None:
        """Schedule one exact identity; duplicate replay does not consume depth again."""
        prior = self._orders.get(order.client_order_id)
        if prior is not None:
            if (prior.order, prior.book, prior.timing, prior.maximum_book_delay_ms) != (
                order,
                book,
                timing,
                maximum_book_delay_ms,
            ):
                raise ValueError("conflicting client order identity")
            return
        self._validate_submission(order, book, timing, maximum_book_delay_ms)
        liquidity = self._books.get(book.source_id)
        if liquidity is None:
            liquidity = BookLiquidity(book)
        elif liquidity.book != book:
            raise ValueError("conflicting recorded book source identity")
        match = liquidity.execute(side=order.side, quantity=order.quantity, limit_price=order.limit_price)
        self._orders[order.client_order_id] = AcceptedIoc(
            len(self._orders) + 1,
            order,
            book,
            timing,
            maximum_book_delay_ms,
            match,
        )
        self._books[book.source_id] = liquidity
        self._latest_book[book.symbol] = book.exchange_time_ms

    def advance_to(self, time_ms: int) -> None:
        """Commit due fills in venue order, preserving their separate fill clocks."""
        require_clock(time_ms, "venue advance time")
        if time_ms < self.clock.now_ms:
            raise ValueError("venue clock cannot move backwards")
        pending = sorted(
            (
                row
                for row in self._orders.values()
                if not row.applied and row.book.exchange_time_ms <= time_ms
            ),
            key=lambda row: (row.book.exchange_time_ms, row.oid),
        )
        for row in pending:
            self.clock.advance_to(max(self.clock.now_ms, row.book.exchange_time_ms))
            row.fills = self._apply(row)
            row.applied = True
        self.clock.advance_to(time_ms)

    def response(self, client_order_id: str) -> dict[str, object] | None:
        """Return a fresh synthetic SDK acknowledgement only after its response time."""
        row = self._known_order(client_order_id)
        if self.clock.now_ms < row.timing.response_ms:
            return None
        self.advance_to(self.clock.now_ms)
        if row.timing.response_lost:
            raise RequestException("recorded response loss after possible IOC execution")
        if row.match.filled_quantity:
            status = {
                "filled": {
                    "oid": row.oid,
                    "totalSz": str(row.match.filled_quantity),
                    "avgPx": str(row.match.vwap),
                }
            }
        else:
            status = {"error": "Order could not immediately match against any resting orders."}
        return {"status": "ok", "response": {"type": "order", "data": {"statuses": [status]}}}

    def order_status(self, client_order_id: str) -> str | None:
        """Expose terminal IOC state only after the declared order-query visibility."""
        row = self._known_order(client_order_id)
        if self.clock.now_ms < row.timing.order_visible_ms:
            return None
        self.advance_to(self.clock.now_ms)
        return "filled" if row.match.disposition == "complete" else "canceled"

    def visible_fills(self) -> tuple[FillEvent, ...]:
        """Expose economic fill records after history availability, without reapplying."""
        self.advance_to(self.clock.now_ms)
        rows = sorted(self._orders.values(), key=lambda row: (row.timing.fill_visible_ms, row.oid))
        return tuple(
            fill for row in rows if row.timing.fill_visible_ms <= self.clock.now_ms for fill in row.fills
        )

    def _known_order(self, identity: str) -> AcceptedIoc:
        if identity not in self._orders:
            raise ValueError(f"unknown order identity: {identity}")
        return self._orders[identity]

    def _validate_submission(
        self,
        order: IocOrder,
        book: RecordedBook,
        timing: ReceiptTiming,
        maximum: int,
    ) -> None:
        require_clock(maximum, "maximum book sampling delay")
        if order.symbol != book.symbol or order.dispatch_time_ms != self.clock.now_ms:
            raise ValueError("IOC book symbol and current dispatch clock must match")
        delay = book.exchange_time_ms - order.arrival_time_ms
        if not 0 <= delay <= maximum:
            raise ValueError("recorded book must follow arrival within the declared sampling window")
        if min(timing.fill_visible_ms, timing.order_visible_ms, timing.response_ms) < book.exchange_time_ms:
            raise ValueError("IOC receipt clocks must not precede the modeled fill")
        if book.exchange_time_ms < self._latest_book.get(book.symbol, 0):
            raise ValueError("recorded book publication cannot move backwards")
        if any(row.order.symbol == order.symbol and not row.applied for row in self._orders.values()):
            raise ValueError("same-symbol pending execution must resolve before another submission")
        view = self.account.snapshot()
        if order.symbol not in view.mark_prices:
            raise ValueError("IOC requires an explicit available account mark for its symbol")
        position = view.positions.get(order.symbol)
        if not order.reduce_only:
            if position is not None:
                raise ValueError("a new opening order requires flat exposure in this replay contract")
        elif position is None or order.quantity > abs(position.quantity_signed):
            raise ValueError("reduction requires sufficient existing exposure")
        elif (position.quantity_signed > 0) == (order.side == "buy") or order.leverage != position.leverage:
            raise ValueError("reduction must oppose the position and preserve its leverage")

    def _apply(self, row: AcceptedIoc) -> tuple[FillEvent, ...]:
        order, fills = row.order, []
        with localcontext() as context:
            context.prec = REPLAY_DECIMAL_PRECISION
            for index, match in enumerate(row.match.matches):
                event = FillEvent(
                    f"{order.client_order_id}:{index}",
                    str(row.oid),
                    order.symbol,
                    order.side,
                    match.quantity,
                    match.price,
                    match.quantity * match.price * order.fee_rate,
                    order.leverage,
                    order.decision_time_ms,
                    order.dispatch_time_ms,
                    row.book.exchange_time_ms,
                    self.clock.next_stamp(),
                    order.reduce_only,
                )
                self.account.apply_fill(event)
                fills.append(event)
        return tuple(fills)
