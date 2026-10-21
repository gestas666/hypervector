"""Independent rational arithmetic over interleaved seven-asset account receipts."""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from itertools import count
from typing import Iterator

from hypervector.research.native_replay_account import AccountView, ExactFillAccount
from hypervector.research.native_replay_events import FillEvent, FundingEvent, Stamp

SYMBOLS = ("BTC", "ETH", "SOL", "HYPE", "xyz:BBB", "xyz:CCC", "xyz:EEE")
INITIAL_CASH = Fraction(10_000)
TOLERANCE_USD = Fraction(1, 10**38)


@dataclass(frozen=True)
class ReferencePosition:
    """Store signed quantity and a rational unit cost, independent of Decimal lots."""

    quantity: Fraction
    unit_cost: Fraction


class FractionOracle:
    """Rebuild cash from cumulative identities instead of incremental Decimal cash."""

    def __init__(self, marks: dict[str, Decimal]) -> None:
        """Start exact rational state with no imports of production arithmetic."""
        self.positions: dict[str, ReferencePosition] = {}
        self.marks = {symbol: Fraction(price) for symbol, price in marks.items()}
        self.realized = self.fees = self.funding = Fraction(0)
        self.checked_views = 0

    def consume_fill(self, event: FillEvent) -> None:
        """Use average unit cost to independently account for one receipt."""
        quantity = Fraction(event.quantity) * (1 if event.side == "buy" else -1)
        price = Fraction(event.price)
        previous = self.positions.get(event.symbol)
        if event.reduce_only:
            assert previous is not None
            self.realized -= quantity * (price - previous.unit_cost)
            remainder = previous.quantity + quantity
            if remainder:
                self.positions[event.symbol] = ReferencePosition(remainder, previous.unit_cost)
            else:
                del self.positions[event.symbol]
        elif previous is None:
            self.positions[event.symbol] = ReferencePosition(quantity, price)
        else:
            total = previous.quantity + quantity
            average = (previous.quantity * previous.unit_cost + quantity * price) / total
            self.positions[event.symbol] = ReferencePosition(total, average)
        self.fees += Fraction(event.fee_usd)

    def check(self, observed: AccountView) -> None:
        """Compare every economic field and exposure against rational identities."""
        unrealized = sum(
            (self.marks[symbol] - position.unit_cost) * position.quantity
            for symbol, position in self.positions.items()
        )
        gross = sum(
            self.marks[symbol] * abs(position.quantity) for symbol, position in self.positions.items()
        )
        margin = sum(abs(position.quantity) * position.unit_cost / 10 for position in self.positions.values())
        cash = INITIAL_CASH + self.realized + self.funding - self.fees
        expected = {
            "cash_usd": cash,
            "realized_gross_usd": self.realized,
            "fees_usd": self.fees,
            "funding_usd": self.funding,
            "unrealized_pnl_usd": unrealized,
            "equity_usd": cash + unrealized,
            "gross_notional_usd": gross,
            "allocated_initial_margin_usd": margin,
        }
        for name, value in expected.items():
            assert abs(Fraction(getattr(observed, name)) - value) <= TOLERANCE_USD, name
        assert observed.positions.keys() == self.positions.keys()
        for symbol, position in self.positions.items():
            actual = observed.positions[symbol]
            assert Fraction(actual.quantity_signed) == position.quantity
            assert abs(Fraction(actual.entry_price) - position.unit_cost) <= TOLERANCE_USD
        self.checked_views += 1


def send_fill(
    book: ExactFillAccount,
    oracle: FractionOracle,
    times: Iterator[int],
    *,
    symbol: str,
    cycle: int,
    origin: int,
    part: int,
    side: str,
    quantity: str,
    price: Decimal,
    reduce_only: bool,
) -> None:
    """Deliver one common source event to structurally different accountants."""
    at = next(times)
    event = FillEvent(
        f"{symbol}/{cycle}/{part}",
        f"{symbol}/{cycle}",
        symbol,
        side,
        Decimal(quantity),
        price,
        Decimal("-0.007") if part == 0 else Decimal("0.009"),
        Decimal("10"),
        origin,
        origin + 1,
        at,
        Stamp(at, 0),
        reduce_only,
    )
    book.apply_fill(event)
    oracle.consume_fill(event)
    oracle.check(book.snapshot())


def initial_portfolio() -> tuple[ExactFillAccount, FractionOracle, dict[str, Decimal]]:
    """Seed both representations from identical explicit capital and marks."""
    marks = {symbol: Decimal(100 + index * 17) for index, symbol in enumerate(SYMBOLS)}
    book = ExactFillAccount(Decimal(INITIAL_CASH.numerator), SYMBOLS)
    oracle = FractionOracle(marks)
    book.mark(Stamp(0, 0), source_time_ms=0, prices=marks)
    oracle.check(book.snapshot())
    return book, oracle, marks


def test_four_seven_asset_cycles_match_rational_accounting_after_every_receipt() -> None:
    """145 views cover mixed directions, recurring cost fractions and late cash."""
    book, oracle, marks = initial_portfolio()
    times = count(1)
    for cycle in range(4):
        origin = next(times)
        for index, symbol in enumerate(SYMBOLS):
            for part, quantity in enumerate(("0.3", "0.4")):
                send_fill(
                    book,
                    oracle,
                    times,
                    symbol=symbol,
                    cycle=cycle,
                    origin=origin,
                    part=part,
                    side="buy" if index % 2 else "sell",
                    quantity=quantity,
                    price=marks[symbol] + part * 3,
                    reduce_only=False,
                )
        at = next(times)
        marks = {symbol: value + (5 if cycle % 2 else -3) for symbol, value in marks.items()}
        book.mark(Stamp(at, 0), source_time_ms=at, prices=marks)
        oracle.marks = {symbol: Fraction(price) for symbol, price in marks.items()}
        oracle.check(book.snapshot())
        for index, symbol in enumerate(SYMBOLS):
            for part, quantity in enumerate(("0.1", "0.6"), start=2):
                send_fill(
                    book,
                    oracle,
                    times,
                    symbol=symbol,
                    cycle=cycle,
                    origin=origin,
                    part=part,
                    side="sell" if index % 2 else "buy",
                    quantity=quantity,
                    price=marks[symbol] + part,
                    reduce_only=True,
                )
            funding = FundingEvent(
                f"{symbol}/{cycle}", symbol, Decimal(index % 3 - 1).scaleb(-2), at, Stamp(next(times), 0)
            )
            book.apply_funding(funding)
            oracle.funding += Fraction(funding.amount_usd)
            oracle.check(book.snapshot())
        assert not book.snapshot().positions
    assert oracle.checked_views == 145
