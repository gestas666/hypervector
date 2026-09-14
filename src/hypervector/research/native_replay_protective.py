"""Explicit mark-triggered stop execution over the shared finite recorded book.

The transformed limit and event ordering are scenario inputs. Trigger-time
crossing may fill once; a GTC remainder requires separate maker queue evidence.
This does not infer maker fills from an L2 touch or claim a venue batch simulator.
"""

from dataclasses import replace
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING

from hypervector.research.native_replay_account import REPLAY_DECIMAL_PRECISION, ReplayPosition
from hypervector.research.native_replay_depth import IocMatch, RecordedBook
from hypervector.research.native_replay_events import FillEvent, require_amount
from hypervector.research.native_replay_sdk_models import ReplayOrderRecord

if TYPE_CHECKING:
    from hypervector.research.native_replay_sdk import ReplaySdk


class ReplayProtectiveExecution:
    """Apply declared protective events using the native SDK's single order/account state."""

    def __init__(self, replay: "ReplaySdk") -> None:
        """Require an offline SDK boundary; no external exchange client is constructed."""
        self.replay = replay

    def activate_stop(self, oid: int, *, mark_time_ms: int, execution_limit: Decimal) -> None:
        """Latch a verified mark crossing and an explicitly modeled transformed GTC limit."""
        row = self._open_order(oid)
        if row.trigger_price is None:
            raise ValueError("stop activation requires an untriggered stop-market order")
        require_amount(execution_limit, "transformed stop limit", positive=True)
        mark = self.replay.observed_mark(row.symbol, mark_time_ms)
        if (row.is_buy and mark < row.trigger_price) or (
            not row.is_buy and mark > row.trigger_price
        ):
            raise ValueError("available mark has not crossed the stop trigger")
        now = self.replay.clock.now_ms
        self.replay.orders[oid] = replace(
            row,
            previous=row,
            trigger_price=None,
            triggered_ms=now,
            limit_price=execution_limit,
            status_ms=now,
            changed_visible_ms=now + self.replay.timing.order_visible_delay_ms,
        )

    def match_stop(self, oid: int, book: RecordedBook) -> tuple[FillEvent, ...]:
        """Match a newly triggered stop once; preserve any unfilled GTC remainder."""
        row = self._open_order(oid)
        self._validate_match(row, book)
        before = self.replay.account.snapshot().positions.get(row.symbol)
        if before is None or (before.quantity_signed < 0) != row.is_buy:
            self._record_match(row, row.remaining, "canceled")
            return ()
        quantity = min(row.remaining, abs(before.quantity_signed))
        match = self.replay.venue.preview_book(
            book,
            side="buy" if row.is_buy else "sell",
            quantity=quantity,
            limit_price=row.limit_price,
        )
        if (
            0 < match.filled_quantity < abs(before.quantity_signed)
            and self.replay.partial_collateral is None
        ):
            raise ValueError(f"partial {row.symbol} close requires an explicit collateral scenario")
        match = self.replay.venue.match_book(
            book,
            side="buy" if row.is_buy else "sell",
            quantity=quantity,
            limit_price=row.limit_price,
        )
        fills = self._apply_fills(row, before, match)
        after = self.replay.account.snapshot().positions.get(row.symbol)
        if fills:
            self.replay.update_fill_collateral(row.symbol, before, after, fills)
        remaining = row.remaining - match.filled_quantity
        status = "filled" if remaining == 0 else "canceled" if after is None else "open"
        self._record_match(row, remaining, status)
        return fills

    def _open_order(self, oid: int) -> ReplayOrderRecord:
        row = self.replay.orders.get(oid)
        if row is None or not row.resting or row.status != "open" or not row.reduce_only:
            raise ValueError("protective execution requires an owned open reduce-only order")
        return row

    def _validate_match(self, row: ReplayOrderRecord, book: RecordedBook) -> None:
        if row.triggered_ms is None:
            raise ValueError("stop matching requires prior mark-trigger activation")
        if row.matched_ms is not None:
            raise ValueError("resting GTC remainder requires explicit maker queue evidence")
        step = Decimal(1).scaleb(-self.replay.markets[row.symbol].metadata.size_decimals)
        if book.symbol != row.symbol or book.quantity_step != step:
            raise ValueError("stop execution book must match the original market and lot grid")
        if book.exchange_time_ms != self.replay.clock.now_ms:
            raise ValueError("stop execution book requires its exact economic clock")

    def _apply_fills(
        self, row: ReplayOrderRecord, before: ReplayPosition, match: IocMatch
    ) -> tuple[FillEvent, ...]:
        fills: list[FillEvent] = []
        now, market = self.replay.clock.now_ms, self.replay.markets[row.symbol]
        with localcontext() as context:
            context.prec = REPLAY_DECIMAL_PRECISION
            for index, level in enumerate(match.matches):
                fill = FillEvent(
                    f"protective:{row.oid}:{now}:{index}",
                    str(row.oid),
                    row.symbol,
                    "buy" if row.is_buy else "sell",
                    level.quantity,
                    level.price,
                    level.quantity * level.price * market.taker_rate,
                    before.leverage,
                    row.created_ms,
                    row.created_ms,
                    now,
                    self.replay.clock.next_stamp(),
                    True,
                )
                self.replay.account.apply_fill(fill)
                gross = (
                    level.quantity
                    * (level.price - before.entry_price)
                    * (1 if before.quantity_signed > 0 else -1)
                )
                self.replay.record_fill(
                    fill,
                    gross=gross,
                    client_id=row.client_id,
                    visible_ms=now + self.replay.timing.fill_visible_delay_ms,
                    crossed=True,
                )
                fills.append(fill)
        return tuple(fills)

    def _record_match(self, row: ReplayOrderRecord, remaining: Decimal, status: str) -> None:
        now = self.replay.clock.now_ms
        self.replay.orders[row.oid] = replace(
            row,
            previous=row,
            remaining=remaining,
            status=status,
            status_ms=now,
            matched_ms=now,
            changed_visible_ms=now + self.replay.timing.order_visible_delay_ms,
        )
