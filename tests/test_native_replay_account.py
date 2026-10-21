"""Economic invariants for causally observed, exact-quantity portfolio fills."""

from dataclasses import replace
from decimal import Decimal

import pytest

from hypervector.research.native_replay_account import ExactFillAccount
from hypervector.research.native_replay_events import FillEvent, FundingEvent, Stamp


def fill(
    identity: str = "first",
    *,
    symbol: str = "BTC",
    side: str = "buy",
    quantity: str = "2",
    price: str = "100",
    fee: str = "1",
    reduce_only: bool = False,
    observed: int = 30,
    sequence: int = 0,
    order: str = "opening",
) -> FillEvent:
    """Construct explicit clocks and economic terms without implicit rounding."""
    return FillEvent(
        identity,
        order,
        symbol,
        side,
        Decimal(quantity),
        Decimal(price),
        Decimal(fee),
        Decimal("10"),
        10,
        20,
        25,
        Stamp(observed, sequence),
        reduce_only,
    )


def account() -> ExactFillAccount:
    """Start one shared account with explicit opening marks."""
    result = ExactFillAccount(Decimal("1000"), ("BTC", "xyz:CCC"))
    result.mark(Stamp(1, 0), source_time_ms=1, prices={"BTC": Decimal("100"), "xyz:CCC": Decimal("200")})
    return result


def test_exact_fills_share_cash_equity_and_keep_decision_origin() -> None:
    """Different fill and observation clocks must not reset the holding origin."""
    book = account()
    assert book.apply_fill(fill())
    assert book.apply_fill(
        fill("short", symbol="xyz:CCC", side="sell", quantity="1", price="200", observed=31)
    )
    book.mark(Stamp(40, 0), source_time_ms=39, prices={"BTC": Decimal("110"), "xyz:CCC": Decimal("180")})
    view = book.snapshot()
    assert view.cash_usd == Decimal("998")
    assert view.unrealized_pnl_usd == Decimal("40")
    assert view.equity_usd == Decimal("1038")
    assert view.gross_notional_usd == Decimal("400")
    assert view.allocated_initial_margin_usd == Decimal("40")
    assert view.positions["BTC"].decision_time_ms == 10
    assert view.positions["BTC"].first_fill_time_ms == 25


def test_partial_fill_weighting_and_partial_reductions() -> None:
    """Fee cash and released allocation reconcile through multiple receipts."""
    book = account()
    book.apply_fill(fill(quantity="1"))
    book.apply_fill(fill("part2", quantity="1", price="120", observed=31))
    first = book.snapshot().positions["BTC"]
    assert first.quantity_signed == Decimal("2")
    assert first.entry_price == Decimal("110")
    assert first.allocated_initial_margin_usd == Decimal("22")
    book.apply_fill(
        fill(
            "close1", side="sell", quantity="0.5", price="130", observed=32, reduce_only=True, order="close1"
        )
    )
    view = book.snapshot()
    assert view.realized_gross_usd == Decimal("10")
    assert view.fees_usd == Decimal("3")
    assert view.cash_usd == Decimal("1007")
    assert view.positions["BTC"].quantity_signed == Decimal("1.5")
    assert view.allocated_initial_margin_usd == Decimal("16.5")
    book.apply_fill(
        fill("close2", side="sell", quantity="1.5", price="90", observed=33, reduce_only=True, order="close2")
    )
    assert not book.snapshot().positions
    assert book.snapshot().cash_usd == Decimal("976")


def test_funding_can_arrive_after_a_position_closed_and_rebates_are_signed() -> None:
    """Late settlement changes cash once without recreating old exposure."""
    book = account()
    book.apply_fill(fill(fee="-0.25"))
    book.apply_fill(
        fill("close", side="sell", price="100", fee="0.25", observed=31, reduce_only=True, order="close")
    )
    settlement = FundingEvent("funding", "BTC", Decimal("-2"), 28, Stamp(40, 0))
    assert book.apply_funding(settlement)
    assert not book.apply_funding(replace(settlement, stamp=Stamp(50, 0)))
    assert book.snapshot().cash_usd == Decimal("998")
    assert book.snapshot().fees_usd == 0
    assert book.snapshot().funding_usd == Decimal("-2")
    assert not book.snapshot().positions


def test_negative_equity_is_reported_without_an_implicit_loss_gate() -> None:
    """Loss and allocated margin pressure remain outcomes of supplied fills."""
    book = account()
    book.apply_fill(fill(quantity="100", side="sell"))
    book.mark(Stamp(40, 0), source_time_ms=40, prices={"BTC": Decimal("200")})
    assert book.snapshot().equity_usd == Decimal("-9001")
    assert book.snapshot().allocated_initial_margin_usd == Decimal("1000")
    assert book.apply_funding(FundingEvent("credit", "BTC", Decimal("1"), 41, Stamp(41, 0)))
    assert book.snapshot().equity_usd == Decimal("-9000")


def test_exact_duplicates_are_idempotent_and_conflicting_duplicates_atomic() -> None:
    """Repeated reconciliation cannot double count or rewrite a venue identity."""
    book = account()
    event = fill()
    book.apply_fill(event)
    before = book.snapshot()
    assert not book.apply_fill(replace(event, stamp=Stamp(90, 0)))
    assert book.snapshot() == before
    with pytest.raises(ValueError, match="conflicting fill identity"):
        book.apply_fill(replace(event, price=Decimal("101"), stamp=Stamp(91, 0)))
    assert book.snapshot() == before


@pytest.mark.parametrize(
    "change, message",
    [
        ({"side": "buy"}, "opposite"),
        ({"quantity": "3"}, "exceeds"),
        ({"symbol": "xyz:CCC"}, "open position"),
    ],
)
def test_invalid_reductions_do_not_mutate_account(change: dict[str, str], message: str) -> None:
    """Reject non-reducing and oversized execution evidence before cash writes."""
    book = account()
    book.apply_fill(fill())
    before = book.snapshot()
    terms = {"side": "sell", "quantity": "1", **change}
    with pytest.raises(ValueError, match=message):
        book.apply_fill(fill("close", **terms, reduce_only=True, observed=31))
    assert book.snapshot() == before


def test_same_timestamp_requires_explicit_increasing_sequence() -> None:
    """A poll's sequential dispatches may share a millisecond, not an order key."""
    book = account()
    book.apply_fill(fill())
    book.apply_fill(fill("second", sequence=1))
    before = book.snapshot()
    with pytest.raises(ValueError, match="observation order"):
        book.apply_fill(fill("third", sequence=1))
    assert book.snapshot() == before


@pytest.mark.parametrize(
    "changes",
    [
        {"decision_time_ms": 21},
        {"dispatch_time_ms": 26},
        {"fill_time_ms": 31},
        {"reduce_only": 1},
        {"side": "long"},
        {"quantity": Decimal("0")},
        {"price": Decimal("NaN")},
        {"fee_usd": Decimal("Infinity")},
        {"leverage": Decimal("0")},
        {"quantity": 1.0},
        {"fill_id": ""},
        {"order_id": ""},
    ],
)
def test_malformed_fill_events_are_rejected(changes: dict[str, object]) -> None:
    """Refuse ambiguous clocks, identities, numeric types and directions."""
    with pytest.raises(ValueError):
        replace(fill(), **changes)


@pytest.mark.parametrize("stamp", [(True, 0), (-1, 0), (1, -1), (1, 0.5)])
def test_invalid_observation_stamps_are_rejected(stamp: tuple[object, object]) -> None:
    """Only nonnegative integer millisecond and sequence values are ordered."""
    with pytest.raises(ValueError):
        Stamp(*stamp)


def test_bad_marks_do_not_partially_update_valid_assets() -> None:
    """A multi-asset publication commits atomically when all marks are valid."""
    book = account()
    book.apply_fill(fill())
    before = book.snapshot()
    with pytest.raises(ValueError, match="price"):
        book.mark(Stamp(40, 0), source_time_ms=39, prices={"BTC": Decimal("200"), "xyz:CCC": Decimal("NaN")})
    assert book.snapshot() == before
    with pytest.raises(ValueError, match="source"):
        book.mark(Stamp(40, 0), source_time_ms=41, prices={"BTC": Decimal("200")})
    assert book.snapshot() == before


def test_fill_requires_explicit_mark_and_configured_symbol() -> None:
    """Execution prices do not silently become a current mark-price feed."""
    book = ExactFillAccount(Decimal("1000"), ("BTC",))
    with pytest.raises(ValueError, match="mark"):
        book.apply_fill(fill())
    with pytest.raises(ValueError, match="configured"):
        book.apply_fill(fill(symbol="xyz:CCC"))
    assert book.snapshot().cash_usd == Decimal("1000")
