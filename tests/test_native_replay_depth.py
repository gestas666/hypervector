"""Exact IOC liquidity accounting and explicit missing/invalid depth outcomes."""

from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from hypervector.research.native_replay_depth import BookLiquidity, ExactLevel, RecordedBook

D = Decimal


def book() -> RecordedBook:
    """Supply finite ascending asks and descending bids on an explicit lot grid."""
    return RecordedBook(
        "fixture:1",
        "xyz:SNDK",
        1100,
        D("0.001"),
        (ExactLevel(D("99.9"), D("0.1")), ExactLevel(D("99.8"), D("0.2"))),
        (ExactLevel(D("100.1"), D("0.1")), ExactLevel(D("100.2"), D("0.2"))),
    )


@pytest.mark.parametrize("side,limit", [("buy", "100.1"), ("sell", "99.9")])
def test_partial_ioc_consumes_only_allowed_levels(side: str, limit: str) -> None:
    """The inclusive limit fills one level and cancels the remaining request."""
    liquidity = BookLiquidity(book())
    result = liquidity.execute(side=side, quantity=D("0.25"), limit_price=D(limit))
    assert result.filled_quantity == D("0.1") and result.unfilled_quantity == D("0.15")
    assert result.disposition == "partial" and result.quote_usd == D(limit) * D("0.1")
    assert result.matches == (ExactLevel(D(limit), D("0.1")),)
    again = liquidity.execute(side=side, quantity=D("0.1"), limit_price=D(limit))
    assert again.disposition == "no_fill" and again.vwap is None
    assert again.quote_usd == 0 and again.matches == ()


@pytest.mark.parametrize("side,limit", [("buy", "100.3"), ("sell", "99.7")])
def test_partial_level_and_independent_cash_conservation(side: str, limit: str) -> None:
    """Sequential orders share remaining liquidity; Decimal costs match rationals."""
    liquidity = BookLiquidity(book())
    first = liquidity.execute(side=side, quantity=D("0.15"), limit_price=D(limit))
    second = liquidity.execute(side=side, quantity=D("0.2"), limit_price=D(limit))
    third = liquidity.execute(side=side, quantity=D("0.01"), limit_price=D(limit))
    assert (first.disposition, second.disposition, third.disposition) == ("complete", "partial", "no_fill")
    assert first.matches[1].quantity == D("0.05") and second.matches[0].quantity == D("0.15")
    levels = book().asks if side == "buy" else book().bids
    oracle = sum(Fraction(row.price) * Fraction(row.quantity) for row in levels)
    assert Fraction(first.quote_usd + second.quote_usd) == oracle
    assert first.filled_quantity + second.filled_quantity == D("0.3")
    assert abs(Fraction(first.vwap) - Fraction(first.quote_usd) / Fraction(first.filled_quantity)) < Fraction(
        1, 10**45
    )


def test_ambient_decimal_precision_does_not_change_matching() -> None:
    """An unrelated caller's low precision cannot alter lot or cash calculations."""
    baseline = BookLiquidity(book()).execute(side="buy", quantity=D("0.251"), limit_price=D("100.2"))
    with localcontext() as context:
        context.prec = 3
        actual = BookLiquidity(book()).execute(side="buy", quantity=D("0.251"), limit_price=D("100.2"))
    assert actual == baseline


@pytest.mark.parametrize(
    "changes",
    [
        {"source_id": ""},
        {"symbol": " SNDK"},
        {"exchange_time_ms": True},
        {"quantity_step": D(0)},
        {"quantity_step": 0.001},
        {"bids": ()},
        {"asks": []},
        {"bids": (ExactLevel(D("100.1"), D("0.1")),)},
        {"asks": tuple(reversed(book().asks))},
        {"bids": tuple(reversed(book().bids))},
        {"asks": (ExactLevel(D("100.1"), D("0.1001")),)},
        {"asks": ("bad",)},
    ],
)
def test_invalid_source_books_fail_explicitly(changes: dict[str, object]) -> None:
    """Reject malformed, crossed, unsorted and off-grid evidence before use."""
    with pytest.raises(ValueError):
        replace(book(), **changes)


@pytest.mark.parametrize("price,quantity", [(D(0), D(1)), (D(1), D(-1)), (D("NaN"), D(1)), (1, D(1))])
def test_invalid_level_values_fail(price: object, quantity: Decimal) -> None:
    """Level values must carry explicit positive finite decimal precision."""
    with pytest.raises(ValueError):
        ExactLevel(price, quantity)


def test_liquidity_requires_a_validated_book() -> None:
    """An arbitrary object cannot bypass source-book validation."""
    with pytest.raises(ValueError, match="RecordedBook"):
        BookLiquidity(None)


@pytest.mark.parametrize(
    "changes",
    [
        {"side": "long"},
        {"quantity": D(0)},
        {"quantity": D("0.0001")},
        {"quantity": 0.1},
        {"limit_price": D("Infinity")},
        {"limit_price": D(-1)},
    ],
)
def test_invalid_request_leaves_liquidity_unchanged(changes: dict[str, object]) -> None:
    """A technical rejection cannot consume visible depth for the next attempt."""
    liquidity = BookLiquidity(book())
    kwargs = {"side": "buy", "quantity": D("0.1"), "limit_price": D("100.2"), **changes}
    with pytest.raises(ValueError):
        liquidity.execute(**kwargs)
    assert liquidity.execute(side="buy", quantity=D("0.3"), limit_price=D("100.2")).disposition == "complete"
