"""Adversarial account boundaries, event identities and immutable snapshots."""

from dataclasses import replace
from decimal import Decimal, localcontext

import pytest

from hypervector.research.native_replay_account import ExactFillAccount
from hypervector.research.native_replay_events import FundingEvent, Stamp
from test_native_replay_account import account, fill


@pytest.mark.parametrize(
    "capital,symbols",
    [
        (Decimal("0"), ("BTC",)),
        (Decimal("NaN"), ("BTC",)),
        (1000, ("BTC",)),
        (Decimal("1000"), ()),
        (Decimal("1000"), ("BTC", "BTC")),
        (Decimal("1000"), ["BTC"]),
        (Decimal("1000"), (" BTC",)),
    ],
)
def test_initial_account_requires_explicit_finite_capital_and_universe(
    capital: object,
    symbols: object,
) -> None:
    """Invalid research inputs fail before the account can be used."""
    with pytest.raises(ValueError):
        ExactFillAccount(capital, symbols)


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"side": "sell"}, "reverse"),
        ({"order_id": "other"}, "retain"),
        ({"leverage": Decimal("5")}, "retain"),
        ({"decision_time_ms": 11}, "retain"),
    ],
)
def test_partial_open_cannot_silently_change_the_bound_position(
    changes: dict[str, object],
    message: str,
) -> None:
    """One native opening order retains direction, leverage and decision clock."""
    book = account()
    book.apply_fill(fill())
    before = book.snapshot()
    with pytest.raises(ValueError, match=message):
        book.apply_fill(replace(fill("next", observed=31), **changes))
    assert book.snapshot() == before


def test_reduction_cannot_relabel_leverage() -> None:
    """A close receipt cannot silently rewrite an open position's allocation."""
    book = account()
    book.apply_fill(fill())
    before = book.snapshot()
    with pytest.raises(ValueError, match="leverage"):
        book.apply_fill(
            replace(fill("close", side="sell", observed=31, reduce_only=True), leverage=Decimal("5"))
        )
    assert book.snapshot() == before


@pytest.mark.parametrize(
    "changes",
    [
        {"event_id": ""},
        {"symbol": " BTC"},
        {"amount_usd": Decimal("NaN")},
        {"effective_time_ms": True},
        {"effective_time_ms": 41},
        {"stamp": None},
    ],
)
def test_malformed_funding_evidence_is_rejected(changes: dict[str, object]) -> None:
    """Late funding is allowed; invalid or future settlement evidence is not."""
    event = FundingEvent("one", "BTC", Decimal("1"), 30, Stamp(40, 0))
    with pytest.raises(ValueError):
        replace(event, **changes)


def test_conflicting_funding_does_not_rewrite_cash() -> None:
    """A repeated ID with altered cash requires explicit correction evidence."""
    book = account()
    event = FundingEvent("one", "BTC", Decimal("1"), 30, Stamp(40, 0))
    book.apply_funding(event)
    before = book.snapshot()
    with pytest.raises(ValueError, match="conflicting funding identity"):
        book.apply_funding(replace(event, amount_usd=Decimal("2")))
    assert book.snapshot() == before


def test_marks_require_causal_order_and_consistent_source_revisions() -> None:
    """Old/future clocks and conflicting same-source marks do not overwrite data."""
    book = account()
    before = book.snapshot()
    for source, price in ((0, "100"), (1, "101")):
        with pytest.raises(ValueError, match="source"):
            book.mark(Stamp(2, 0), source_time_ms=source, prices={"BTC": Decimal(price)})
        assert book.snapshot() == before
    with pytest.raises(ValueError, match="Stamp"):
        book.mark(None, source_time_ms=1, prices={"BTC": Decimal("100")})
    with pytest.raises(ValueError, match="nonempty"):
        book.mark(Stamp(2, 0), source_time_ms=2, prices={})
    book.mark(Stamp(2, 0), source_time_ms=1, prices={"BTC": Decimal("100")})
    assert book.snapshot().stamp == Stamp(2, 0)


def test_snapshot_is_detached_and_read_only() -> None:
    """Later fills cannot mutate the already observed portfolio view."""
    book = account()
    book.apply_fill(fill())
    before = book.snapshot()
    with pytest.raises(TypeError):
        before.positions["BTC"] = before.positions["BTC"]
    book.apply_fill(fill("second", observed=31))
    assert before.positions["BTC"].quantity_signed == Decimal("2")
    assert book.snapshot().positions["BTC"].quantity_signed == Decimal("4")


def test_arithmetic_does_not_inherit_ambient_decimal_precision() -> None:
    """The declared replay precision is stable under unrelated caller settings."""
    views = []
    for precision in (4, 28, 80):
        with localcontext() as context:
            context.prec = precision
            book = account()
            book.apply_fill(fill(quantity="0.333333", price="123.456789", fee="0.1234567"))
            views.append(book.snapshot())
    assert views[0] == views[1] == views[2]


@pytest.mark.parametrize("changes", [{"stamp": None}, {"fill_time_ms": True}, {"symbol": 1}])
def test_additional_malformed_fill_boundaries(changes: dict[str, object]) -> None:
    """Unusable stamps and numeric identities fail at event construction."""
    with pytest.raises(ValueError):
        replace(fill(), **changes)
