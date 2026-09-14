"""Stateful offline IOC execution with separate economics and receipt visibility.

Only IOC execution is implemented here. Stops, resting targets, collateral
transfers, liquidation, rate limits and a complete SDK port remain separate
integration work. Recorded snapshot liquidity and timing are declared scenarios.
"""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, localcontext

from requests import RequestException

from hypervector.research.native_replay_account import ExactFillAccount, REPLAY_DECIMAL_PRECISION
from hypervector.research.native_replay_clock import ReplayClock
from hypervector.research.native_replay_depth import (
    BookLiquidity,
    IocMatch,
    RecordedBook,
    validate_lot_quantity,
)
from hypervector.research.native_replay_events import FillEvent, require_clock
from hypervector.research.native_replay_receipts import AcceptedIoc, IocOrder, ReceiptTiming

__all__ = ["IocOrder", "ReceiptTiming", "RecordedIocVenue"]


class RecordedIocVenue:
    """Drive exact shared economics without constructing an SDK client or signer."""

    def __init__(
        self,
        account: ExactFillAccount,
        clock: ReplayClock,
        *,
        oid_allocator: Callable[[], int] | None = None,
    ) -> None:
        """Use explicit account/clock ownership and no live configuration or I/O."""
        self.account, self.clock = account, clock
        self._orders: dict[str, AcceptedIoc] = {}
        self._books: dict[str, BookLiquidity] = {}
        self._latest_book: dict[str, int] = {}
        self._source_ids: dict[tuple[str, int], str] = {}
        self._consumed_ms: dict[str, int] = {}
        self._oid_allocator = oid_allocator or (lambda: len(self._orders) + 1)

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
        liquidity = self._book_liquidity(book)
        validate_lot_quantity(order.quantity, book.quantity_step)
        oid = self._allocate_oid()
        self._orders[order.client_order_id] = AcceptedIoc(
            oid,
            order,
            book,
            timing,
            maximum_book_delay_ms,
        )
        self._books[book.source_id] = liquidity
        self._source_ids[(book.symbol, book.exchange_time_ms)] = book.source_id
        self._latest_book[book.symbol] = book.exchange_time_ms

    def match_book(
        self, book: RecordedBook, *, side: str, quantity: Decimal, limit_price: Decimal
    ) -> IocMatch:
        """Consume shared recorded depth only at its declared economic execution clock."""
        if book.exchange_time_ms != self.clock.now_ms:
            raise ValueError("book matching requires the exact economic clock")
        if book.exchange_time_ms < self._consumed_ms.get(book.symbol, 0):
            raise ValueError("consumed recorded book cannot move backwards")
        liquidity = self._book_liquidity(book)
        match = liquidity.execute(side=side, quantity=quantity, limit_price=limit_price)
        self._books[book.source_id] = liquidity
        self._source_ids[(book.symbol, book.exchange_time_ms)] = book.source_id
        self._consumed_ms[book.symbol] = book.exchange_time_ms
        return match

    def preview_book(
        self, book: RecordedBook, *, side: str, quantity: Decimal, limit_price: Decimal
    ) -> IocMatch:
        """Validate a partial-account scenario against remaining depth without consuming it."""
        if book.exchange_time_ms != self.clock.now_ms:
            raise ValueError("book matching requires the exact economic clock")
        if book.exchange_time_ms < self._consumed_ms.get(book.symbol, 0):
            raise ValueError("consumed recorded book cannot move backwards")
        return deepcopy(self._book_liquidity(book)).execute(
            side=side, quantity=quantity, limit_price=limit_price
        )

    def _book_liquidity(self, book: RecordedBook) -> BookLiquidity:
        prior = self._books.get(book.source_id)
        if prior is not None and prior.book != book:
            raise ValueError("conflicting recorded book source identity")
        identity = self._source_ids.get((book.symbol, book.exchange_time_ms))
        if identity is not None and identity != book.source_id:
            raise ValueError("recorded source clock cannot acquire a second liquidity identity")
        return prior if prior is not None else BookLiquidity(book)

    def execution(self, client_order_id: str) -> AcceptedIoc:
        """Return detached simulation truth; callers must separately enforce receipt visibility."""
        return replace(self._known_order(client_order_id))

    def _allocate_oid(self) -> int:
        oid = self._oid_allocator()
        if type(oid) is not int or oid <= 0 or any(row.oid == oid for row in self._orders.values()):
            raise ValueError("allocated replay order ID must be a unique positive integer")
        return oid

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
        match = row.completed_match
        if match.filled_quantity:
            status = {
                "filled": {
                    "oid": row.oid,
                    "totalSz": str(match.filled_quantity),
                    "avgPx": str(match.vwap),
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
        return "filled" if row.completed_match.disposition == "complete" else "canceled"

    def visible_fills(self) -> tuple[FillEvent, ...]:
        """Expose economic fill records after history availability, without reapplying."""
        self.advance_to(self.clock.now_ms)
        rows = sorted(self._orders.values(), key=lambda row: (row.timing.fill_visible_ms, row.oid))
        return tuple(
            fill
            for row in rows
            if row.timing.fill_visible_ms <= self.clock.now_ms
            for fill in row.fills
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
            raise ValueError(
                "recorded book must follow arrival within the declared sampling window"
            )
        if (
            min(timing.fill_visible_ms, timing.order_visible_ms, timing.response_ms)
            < book.exchange_time_ms
        ):
            raise ValueError("IOC receipt clocks must not precede the modeled fill")
        if book.exchange_time_ms < self._latest_book.get(book.symbol, 0):
            raise ValueError("recorded book publication cannot move backwards")
        if any(
            row.order.symbol == order.symbol and not row.applied for row in self._orders.values()
        ):
            raise ValueError("same-symbol pending execution must resolve before another submission")
        view = self.account.snapshot()
        if order.symbol not in view.mark_prices:
            raise ValueError("IOC requires an explicit available account mark for its symbol")
        position = view.positions.get(order.symbol)
        if not order.reduce_only:
            if position is not None:
                raise ValueError(
                    "a new opening order requires flat exposure in this replay contract"
                )
        elif position is None or order.quantity > abs(position.quantity_signed):
            raise ValueError("reduction requires sufficient existing exposure")
        elif (position.quantity_signed > 0) == (
            order.side == "buy"
        ) or order.leverage != position.leverage:
            raise ValueError("reduction must oppose the position and preserve its leverage")

    def _apply(self, row: AcceptedIoc) -> tuple[FillEvent, ...]:
        order, fills = row.order, []
        with localcontext() as context:
            context.prec = REPLAY_DECIMAL_PRECISION
            row.position_before = self.account.snapshot().positions.get(order.symbol)
            row.match = self._match_order(row)
            for index, match in enumerate(row.completed_match.matches):
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
            row.position_after = self.account.snapshot().positions.get(order.symbol)
        return tuple(fills)

    def _match_order(self, row: AcceptedIoc) -> IocMatch:
        order, position = row.order, row.position_before
        available = order.quantity
        if not order.reduce_only and position is not None:
            raise ValueError("opening execution requires exposure to remain flat at matching")
        if order.reduce_only:
            if position is None or (position.quantity_signed > 0) == (order.side == "buy"):
                return IocMatch(
                    order.quantity, (), Decimal(0), order.quantity, Decimal(0), None, "no_fill"
                )
            if position.leverage != order.leverage:
                raise ValueError("reduction leverage changed before economic matching")
            available = min(available, abs(position.quantity_signed))
        match = self.match_book(
            row.book, side=order.side, quantity=available, limit_price=order.limit_price
        )
        return replace(
            match,
            requested_quantity=order.quantity,
            unfilled_quantity=order.quantity - match.filled_quantity,
            disposition="no_fill"
            if not match.filled_quantity
            else "complete"
            if match.filled_quantity == order.quantity
            else "partial",
        )
