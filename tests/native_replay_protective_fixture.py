"""Prescribed protective executions through actual offline native engine ports.

Books, mark crossings, execution limits and target fills are explicit synthetic
scenarios. Price touching a target does not infer a queue fill. This fixture
currently closes full remaining exposure, so no partial collateral is invented.
"""

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from native_replay_engine_fixture import FEE_RATE, SIZE_DECIMALS
from native_replay_scheduled_fixture import ScheduledEngineFixture

from hypervector.research.native_replay_account import ReplayPosition
from hypervector.research.native_replay_depth import (
    BookLiquidity,
    ExactLevel,
    IocMatch,
    RecordedBook,
)
from hypervector.research.native_replay_events import FillEvent

D = Decimal


class ProtectiveEngineFixture(ScheduledEngineFixture):
    """Supply full protective receipts, sampled books and explicit empty funding."""

    def __init__(self, root: Path) -> None:
        """Construct only inherited offline SDK doubles and synthetic source readers."""
        super().__init__(root, lost=None)
        self._info.l2_snapshot.side_effect = self._telemetry_book
        self._info.user_funding_history.return_value = []

    def fill_owned_order(self, oid: int, *, history_delay_ms: int) -> None:
        """Execute the selected stop/target at finite synthetic depth between polls."""
        assert history_delay_ms >= 0
        wire = self.orders[oid]
        symbol = str(wire["coin"])
        before = self.account.snapshot().positions[symbol]
        quantity = min(D(str(wire["sz"])), abs(before.quantity_signed))
        assert quantity == abs(before.quantity_signed), "partial collateral remains unqualified"
        reference = D(str(wire["triggerPx"] if wire["isTrigger"] else wire["limitPx"]))
        self.clock.advance_to(self.clock.now_ms + 1000)
        self.marks[symbol] = reference
        self.account.mark(
            self.clock.next_stamp(), source_time_ms=self.clock.now_ms, prices={symbol: reference}
        )
        book = self._execution_book(symbol, quantity, reference, wire["side"] == "B")
        side = "buy" if wire["side"] == "B" else "sell"
        if wire["isTrigger"]:
            assert (before.quantity_signed > 0) == (side == "sell")
            limit = book.asks[-1].price if side == "buy" else book.bids[-1].price
        else:
            limit = reference
        match = BookLiquidity(book).execute(side=side, quantity=quantity, limit_price=limit)
        assert match.disposition == "complete", "full protective fixture needs complete depth"
        self._apply_protective_match(oid, wire, before, match, history_delay_ms)
        del self.collateral[symbol]
        del self.orders[oid]
        row = self.scheduled[oid]
        row.status, row.status_time_ms, row.visible_at_ms = (
            "filled",
            self.clock.now_ms,
            self.clock.now_ms,
        )
        row.wire["sz"] = "0.0"

    def _apply_protective_match(
        self,
        oid: int,
        wire: Mapping[str, object],
        before: ReplayPosition,
        match: IocMatch,
        history_delay_ms: int,
    ) -> None:
        symbol = str(wire["coin"])
        side = "buy" if wire["side"] == "B" else "sell"
        for index, level in enumerate(match.matches):
            event = FillEvent(
                f"protective:{oid}:{index}",
                str(oid),
                symbol,
                side,
                level.quantity,
                level.price,
                level.quantity * level.price * FEE_RATE,
                before.leverage,
                int(wire["timestamp"]),
                int(wire["timestamp"]),
                self.clock.now_ms,
                self.clock.next_stamp(),
                True,
            )
            self.account.apply_fill(event)
            gross = (
                level.quantity
                * (level.price - before.entry_price)
                * (1 if before.quantity_signed > 0 else -1)
            )
            self._record_fill(event, gross, wire["cloid"])
            tid = len(self.fills)
            self.fills[-1]["tid"] = tid
            self.fill_visible_at[tid] = self.clock.now_ms + history_delay_ms

    def _execution_book(
        self, symbol: str, quantity: Decimal, reference: Decimal, is_buy: bool
    ) -> RecordedBook:
        """Prescribe one executable level; this is not a historical queue-fill model."""
        step = D(1).scaleb(-SIZE_DECIMALS[symbol])
        bid = reference - step if is_buy else reference
        ask = reference if is_buy else reference + step
        return RecordedBook(
            f"synthetic:protective:{symbol}:{self.clock.now_ms}",
            symbol,
            self.clock.now_ms,
            step,
            (ExactLevel(bid, quantity),),
            (ExactLevel(ask, quantity),),
        )

    def _telemetry_book(self, symbol: str) -> dict[str, object]:
        """Expose a fresh sampled midpoint observation without implying an execution."""
        mark = self.marks[symbol]
        return {
            "coin": symbol,
            "time": self.clock.now_ms,
            "levels": [
                [{"px": str(mark - D("0.01")), "sz": "100", "n": 1}],
                [{"px": str(mark + D("0.01")), "sz": "100", "n": 1}],
            ],
        }
