"""Exact finite IOC matching; archive books are evidence, not guaranteed liquidity.

The existing float market walker and SNDK cap wrapper remain prior art. This
component preserves individual decimal fills and consumed depth across orders.
It accepts the actual submitted limit; SDK price rounding belongs upstream.
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from hypervector.research.native_replay_account import REPLAY_DECIMAL_PRECISION
from hypervector.research.native_replay_events import require_amount, require_clock, require_name

ZERO = Decimal(0)


@dataclass(frozen=True)
class ExactLevel:
    """An explicit price and base quantity from a level or simulated fill."""

    price: Decimal
    quantity: Decimal

    def __post_init__(self) -> None:
        """Reject nondecimal, nonfinite or nonpositive book quantities/prices."""
        require_amount(self.price, "level price", positive=True)
        require_amount(self.quantity, "level quantity", positive=True)


@dataclass(frozen=True)
class RecordedBook:
    """One source-identified exchange-clock snapshot on an explicit asset lot grid.

    Historical retrieval time does not establish realtime strategy availability.
    A separate acquisition/receipt schedule must supply that evidence.
    """

    source_id: str
    symbol: str
    exchange_time_ms: int
    quantity_step: Decimal
    bids: tuple[ExactLevel, ...]
    asks: tuple[ExactLevel, ...]

    def __post_init__(self) -> None:
        """Validate complete, strictly ordered, noncrossed recorded depth."""
        require_name(self.source_id, "book source ID")
        require_name(self.symbol, "book symbol")
        require_clock(self.exchange_time_ms, "book exchange time")
        require_amount(self.quantity_step, "quantity step", positive=True)
        for side, levels in (("buy", self.asks), ("sell", self.bids)):
            _validate_levels(levels, side, self.quantity_step)
        if self.bids[0].price >= self.asks[0].price:
            raise ValueError("recorded book must not be crossed or locked")


@dataclass(frozen=True)
class IocMatch:
    """Finite matched quantities; the unfilled IOC remainder does not rest."""

    requested_quantity: Decimal
    matches: tuple[ExactLevel, ...]
    filled_quantity: Decimal
    unfilled_quantity: Decimal
    quote_usd: Decimal
    vwap: Decimal | None
    disposition: str


class BookLiquidity:
    """Consume a snapshot's visible levels once until an explicit new publication."""

    def __init__(self, book: RecordedBook) -> None:
        """Retain the immutable original and independent remaining bid/ask tuples."""
        if not isinstance(book, RecordedBook):
            raise ValueError("liquidity requires a validated RecordedBook")
        self.book = book
        self._levels = {"buy": book.asks, "sell": book.bids}

    def execute(self, *, side: str, quantity: Decimal, limit_price: Decimal) -> IocMatch:
        """Match only lots at or better than the submitted inclusive limit."""
        if side not in ("buy", "sell"):
            raise ValueError("IOC side must be buy or sell")
        require_amount(quantity, "IOC quantity", positive=True)
        require_amount(limit_price, "IOC limit", positive=True)
        _require_lot(quantity, self.book.quantity_step)
        with localcontext() as context:
            context.prec = REPLAY_DECIMAL_PRECISION
            matches, remaining = _walk(self._levels[side], side, quantity, limit_price)
            filled = sum((row.quantity for row in matches), ZERO)
            quote = sum((row.quantity * row.price for row in matches), ZERO)
            result = IocMatch(
                quantity,
                matches,
                filled,
                quantity - filled,
                quote,
                quote / filled if filled else None,
                "no_fill" if not filled else "complete" if filled == quantity else "partial",
            )
        self._levels[side] = remaining
        return result


def _require_lot(quantity: Decimal, step: Decimal) -> None:
    with localcontext() as context:
        context.prec = REPLAY_DECIMAL_PRECISION
        if quantity % step:
            raise ValueError("quantity must be an exact multiple of the asset lot step")


def _validate_levels(levels: tuple[ExactLevel, ...], side: str, step: Decimal) -> None:
    if not isinstance(levels, tuple) or not levels:
        raise ValueError("recorded book sides must be nonempty level tuples")
    for row in levels:
        if not isinstance(row, ExactLevel):
            raise ValueError("recorded book sides require ExactLevel values")
        _require_lot(row.quantity, step)
    for left, right in zip(levels, levels[1:]):
        if (side == "buy" and left.price >= right.price) or (side == "sell" and left.price <= right.price):
            raise ValueError("recorded book levels must have strictly ordered prices")


def _walk(
    levels: tuple[ExactLevel, ...],
    side: str,
    quantity: Decimal,
    limit: Decimal,
) -> tuple[tuple[ExactLevel, ...], tuple[ExactLevel, ...]]:
    matches, remaining = [], []
    for row in levels:
        eligible = row.price <= limit if side == "buy" else row.price >= limit
        take = min(quantity, row.quantity) if eligible else ZERO
        if take:
            matches.append(ExactLevel(row.price, take))
            quantity -= take
        if row.quantity > take:
            remaining.append(ExactLevel(row.price, row.quantity - take))
    return tuple(matches), tuple(remaining)
