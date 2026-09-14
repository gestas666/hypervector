"""Partial protective receipts with explicitly supplied collateral and order remainder."""

from decimal import Decimal, ROUND_DOWN
from pathlib import Path

from native_replay_engine_fixture import SIZE_DECIMALS
from native_replay_protective_fixture import ProtectiveEngineFixture

from hypervector.research.native_replay_depth import BookLiquidity
from hypervector.research.native_replay_events import FillEvent
from hypervector.research.native_replay_unified import IsolatedCollateral

D = Decimal


class PartialProtectiveFixture(ProtectiveEngineFixture):
    """Apply exact partial economics without asserting a universal collateral-release rule."""

    def __init__(self, root: Path) -> None:
        """Retain the actual engines and declared offline source/SDK ports."""
        super().__init__(root)

    def fill_partial_protection(
        self,
        oid: int,
        *,
        remaining_collateral: IsolatedCollateral,
        history_delay_ms: int,
        remainder_open: bool,
        fee_rate: Decimal,
    ) -> None:
        """Execute half the current exposure with explicit fee and remaining-order inputs."""
        wire = self.orders[oid]
        symbol = str(wire["coin"])
        before = self.account.snapshot().positions[symbol]
        quantity = _partial_quantity(symbol, before.quantity_signed)
        assert history_delay_ms >= 0 and fee_rate >= 0
        reference = D(str(wire["triggerPx"] if wire["isTrigger"] else wire["limitPx"]))
        self.clock.advance_to(self.clock.now_ms + 1000)
        self.marks[symbol] = reference
        self.account.mark(
            self.clock.next_stamp(), source_time_ms=self.clock.now_ms, prices={symbol: reference}
        )
        side = "buy" if wire["side"] == "B" else "sell"
        book = self._execution_book(symbol, quantity, reference, side == "buy")
        match = BookLiquidity(book).execute(side=side, quantity=quantity, limit_price=reference)
        assert match.disposition == "complete" and len(match.matches) == 1
        event = FillEvent(
            f"protective:{oid}:{self.clock.now_ms}",
            str(oid),
            symbol,
            side,
            quantity,
            reference,
            quantity * reference * fee_rate,
            before.leverage,
            int(wire["timestamp"]),
            int(wire["timestamp"]),
            self.clock.now_ms,
            self.clock.next_stamp(),
            True,
        )
        self.account.apply_fill(event)
        self._record_partial_reduction(
            oid,
            event,
            before.entry_price,
            before.quantity_signed,
            history_delay_ms,
            remaining_collateral,
        )
        self._order_remainder(oid, quantity, remainder_open)

    def _record_partial_reduction(
        self,
        oid: int,
        event: FillEvent,
        entry_price: Decimal,
        original_size: Decimal,
        history_delay_ms: int,
        remaining_collateral: IsolatedCollateral,
    ) -> None:
        wire = self.orders[oid]
        gross = event.quantity * (event.price - entry_price) * (1 if original_size > 0 else -1)
        self._record_fill(event, gross, wire["cloid"])
        tid = len(self.fills)
        self.fills[-1]["tid"] = tid
        self.fills[-1]["crossed"] = bool(wire["isTrigger"])
        self.fill_visible_at[tid] = self.clock.now_ms + history_delay_ms
        self.collateral[event.symbol] = remaining_collateral

    def _order_remainder(self, oid: int, executed: Decimal, remains_open: bool) -> None:
        wire = self.orders[oid]
        remaining = D(str(wire["sz"])) - executed
        assert remaining > 0
        row = self.scheduled[oid]
        wire["sz"] = row.wire["sz"] = str(remaining)
        row.status_time_ms = row.visible_at_ms = self.clock.now_ms
        row.status = "open" if remains_open else "canceled"
        if not remains_open:
            del self.orders[oid]


def _partial_quantity(symbol: str, original_size: Decimal) -> Decimal:
    step = D(1).scaleb(-SIZE_DECIMALS[symbol])
    quantity = (abs(original_size) / 2).quantize(step, rounding=ROUND_DOWN)
    assert D(0) < quantity < abs(original_size)
    return quantity
