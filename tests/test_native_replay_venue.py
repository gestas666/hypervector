"""Scheduled IOC economics, late visibility and ambiguous response recovery."""

from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest
from requests import RequestException

from hypervector.research.native_replay_account import ExactFillAccount
from hypervector.research.native_replay_clock import ReplayClock
from hypervector.research.native_replay_venue import IocOrder, ReceiptTiming, RecordedIocVenue
from test_native_replay_depth import book

D = Decimal


def venue() -> RecordedIocVenue:
    """Start flat at an explicit observed mark, without constructing SDK clients."""
    clock = ReplayClock(1000)
    account = ExactFillAccount(D(5000), ("xyz:CCC",))
    account.mark(clock.next_stamp(), source_time_ms=1000, prices={"xyz:CCC": D(100)})
    return RecordedIocVenue(account, clock)


def order() -> IocOrder:
    """Prescribe a submitted limit/quantity and a separate arrival clock."""
    return IocOrder(
        "order:1", "xyz:CCC", "buy", D("0.25"), D("100.2"), D(10), D("0.0009"), 900, 1000, 1050, False
    )


def timing() -> ReceiptTiming:
    """Make account exposure observable before fill history and order status."""
    return ReceiptTiming(fill_visible_ms=1300, order_visible_ms=1400, response_ms=1200, response_lost=False)


def test_execution_is_distinct_from_ack_fill_and_status_visibility() -> None:
    """No fill or status is visible before its clock; quantity is never resized."""
    replay = venue()
    replay.submit(order(), book(), timing(), maximum_book_delay_ms=50)
    assert replay.account.snapshot().positions == {} and replay.response("order:1") is None
    replay.advance_to(1100)
    assert replay.account.snapshot().positions["xyz:CCC"].quantity_signed == D("0.25")
    assert replay.visible_fills() == () and replay.order_status("order:1") is None
    replay.advance_to(1200)
    ack = replay.response("order:1")
    assert ack["response"]["data"]["statuses"][0]["filled"]["totalSz"] == "0.25"
    assert replay.visible_fills() == ()
    replay.advance_to(1300)
    fills = replay.visible_fills()
    assert len(fills) == 2 and [row.quantity for row in fills] == [D("0.1"), D("0.15")]
    assert all(row.fill_time_ms == 1100 and row.decision_time_ms == 900 for row in fills)
    assert replay.order_status("order:1") is None
    replay.advance_to(1400)
    assert replay.order_status("order:1") == "filled"
    expected_fee = sum(Fraction(row.price) * Fraction(row.quantity) * Fraction(9, 10000) for row in fills)
    assert Fraction(replay.account.snapshot().fees_usd) == expected_fee


def test_lost_response_preserves_filled_exposure_and_duplicate_identity() -> None:
    """Reconciliation can discover a fill after transport failure without re-entry."""
    replay = venue()
    lost = replace(timing(), response_lost=True)
    replay.submit(order(), book(), lost, maximum_book_delay_ms=50)
    replay.advance_to(1200)
    before = replay.account.snapshot()
    with pytest.raises(RequestException, match="recorded response loss"):
        replay.response("order:1")
    replay.submit(order(), book(), lost, maximum_book_delay_ms=50)
    assert replay.account.snapshot() == before
    with pytest.raises(ValueError, match="conflicting client"):
        replay.submit(replace(order(), quantity=D("0.1")), book(), lost, maximum_book_delay_ms=50)
    replay.advance_to(1400)
    assert len(replay.visible_fills()) == 2 and replay.order_status("order:1") == "filled"


def test_zero_fill_has_no_economic_mutation_and_partial_remainder_is_canceled() -> None:
    """A tight limit returns explicit no-match; partial IOC quantity does not rest."""
    replay = venue()
    replay.submit(replace(order(), limit_price=D(100)), book(), timing(), maximum_book_delay_ms=50)
    replay.advance_to(1400)
    assert replay.account.snapshot().cash_usd == 5000 and replay.visible_fills() == ()
    assert replay.order_status("order:1") == "canceled"
    assert (
        "could not immediately match"
        in replay.response("order:1")["response"]["data"]["statuses"][0]["error"]
    )
    partial = venue()
    partial.submit(replace(order(), limit_price=D("100.1")), book(), timing(), maximum_book_delay_ms=50)
    partial.advance_to(1400)
    assert partial.account.snapshot().positions["xyz:CCC"].quantity_signed == D("0.1")
    assert partial.order_status("order:1") == "canceled"
    assert partial.response("order:1")["response"]["data"]["statuses"][0]["filled"]["totalSz"] == "0.1"


def test_partial_close_preserves_entry_origin_and_independent_cash() -> None:
    """Exact economic reduction is qualified; venue collateral transfer is separate."""
    replay = venue()
    replay.submit(order(), book(), timing(), maximum_book_delay_ms=50)
    replay.advance_to(1400)
    closing = replace(
        order(),
        client_order_id="close:1",
        side="sell",
        quantity=D("0.15"),
        limit_price=D("99.9"),
        decision_time_ms=1400,
        dispatch_time_ms=1400,
        arrival_time_ms=1450,
        reduce_only=True,
    )
    closing_book = replace(book(), source_id="fixture:2", exchange_time_ms=1500)
    closing_timing = ReceiptTiming(1600, 1600, 1600, False)
    replay.submit(closing, closing_book, closing_timing, maximum_book_delay_ms=50)
    replay.advance_to(1600)
    view = replay.account.snapshot()
    assert view.positions["xyz:CCC"].quantity_signed == D("0.15")
    assert view.positions["xyz:CCC"].decision_time_ms == 900
    gross = Fraction("0.1") * (Fraction("99.9") - Fraction("100.16"))
    assert Fraction(view.realized_gross_usd) == gross
    assert Fraction(view.cash_usd) == Fraction(5000) + gross - Fraction(view.fees_usd)


@pytest.mark.parametrize(
    "changes",
    [
        {"client_order_id": ""},
        {"side": "short"},
        {"quantity": D(-1)},
        {"limit_price": D("NaN")},
        {"leverage": D(0)},
        {"fee_rate": 0.001},
        {"decision_time_ms": 1001},
        {"arrival_time_ms": 999},
        {"reduce_only": 1},
    ],
)
def test_invalid_order_fails_before_submission(changes: dict[str, object]) -> None:
    """Malformed identity, amounts and clocks cannot create accepted orders."""
    with pytest.raises(ValueError):
        replace(order(), **changes)


@pytest.mark.parametrize(
    "changes", [{"fill_visible_ms": True}, {"order_visible_ms": -1}, {"response_lost": 1}]
)
def test_invalid_receipt_types_fail(changes: dict[str, object]) -> None:
    """Receipt latency inputs must be explicit nonnegative clocks and booleans."""
    with pytest.raises(ValueError):
        replace(timing(), **changes)


@pytest.mark.parametrize(
    "case",
    [
        "foreign",
        "stale_book",
        "sampling_gap",
        "early_response",
        "off_grid",
        "wrong_dispatch",
        "reduce_flat",
        "unknown_mark",
    ],
)
def test_invalid_submission_preserves_state(case: str) -> None:
    """Technical missing evidence fails before consuming liquidity or exposing fills."""
    replay, request, source, receipts, maximum = venue(), order(), book(), timing(), 50
    if case == "foreign":
        source = replace(source, symbol="BTC")
    elif case == "stale_book":
        source = replace(source, exchange_time_ms=1049)
    elif case == "sampling_gap":
        maximum = 49
    elif case == "early_response":
        receipts = replace(receipts, response_ms=1099)
    elif case == "off_grid":
        request = replace(request, quantity=D("0.2501"))
    elif case == "wrong_dispatch":
        request = replace(request, dispatch_time_ms=1001)
    elif case == "reduce_flat":
        request = replace(request, reduce_only=True)
    else:
        request, source = replace(request, symbol="BTC"), replace(source, symbol="BTC")
    before = replay.account.snapshot()
    with pytest.raises(ValueError):
        replay.submit(request, source, receipts, maximum_book_delay_ms=maximum)
    assert replay.account.snapshot() == before and replay.visible_fills() == ()


def test_foreign_account_mutation_and_repeated_book_conflict_fail_explicitly() -> None:
    """The replay refuses ambiguous ownership instead of fabricating valid recovery."""
    replay = venue()
    replay.submit(order(), book(), timing(), maximum_book_delay_ms=50)
    with pytest.raises(ValueError, match="pending"):
        replay.submit(replace(order(), client_order_id="second"), book(), timing(), maximum_book_delay_ms=50)
    with pytest.raises(ValueError, match="unknown order"):
        replay.response("absent")
    with pytest.raises(ValueError, match="backwards"):
        replay.advance_to(999)


def test_venue_arithmetic_ignores_ambient_precision() -> None:
    """The venue fee and account schedule preserve exact arithmetic context."""
    baseline = venue()
    baseline.submit(order(), book(), timing(), maximum_book_delay_ms=50)
    baseline.advance_to(1400)
    other = venue()
    with localcontext() as context:
        context.prec = 3
        other.submit(order(), book(), timing(), maximum_book_delay_ms=50)
        other.advance_to(1400)
    assert other.account.snapshot() == baseline.account.snapshot()


def test_repeated_book_preserves_identity_and_new_publications_cannot_regress() -> None:
    """A fresh order cannot alter or roll back a previously accepted book identity."""
    replay = venue()
    no_fill = replace(order(), limit_price=D(100))
    immediate = ReceiptTiming(1100, 1100, 1100, False)
    replay.submit(no_fill, book(), immediate, maximum_book_delay_ms=50)
    with pytest.raises(ValueError, match="backwards"):
        replay.submit(
            replace(no_fill, client_order_id="earlier"),
            replace(book(), exchange_time_ms=1050),
            immediate,
            maximum_book_delay_ms=50,
        )
    replay.advance_to(1100)
    next_order = replace(
        no_fill, client_order_id="next", decision_time_ms=1100, dispatch_time_ms=1100, arrival_time_ms=1100
    )
    replay.submit(next_order, book(), immediate, maximum_book_delay_ms=0)
    replay.advance_to(1100)
    changed = replace(book(), quantity_step=D("0.0001"))
    with pytest.raises(ValueError, match="conflicting recorded book"):
        replay.submit(
            replace(next_order, client_order_id="changed"), changed, immediate, maximum_book_delay_ms=0
        )


@pytest.mark.parametrize("case", ["second_open", "oversized_close", "wrong_side", "wrong_leverage"])
def test_reject_invalid_existing_position_actions_before_consuming_depth(case: str) -> None:
    """The one-position model refuses flips, excess reductions and altered leverage."""
    replay = venue()
    replay.submit(order(), book(), timing(), maximum_book_delay_ms=50)
    replay.advance_to(1400)
    request = replace(
        order(),
        client_order_id="close",
        decision_time_ms=1400,
        dispatch_time_ms=1400,
        arrival_time_ms=1450,
        reduce_only=True,
        side="sell",
    )
    if case == "second_open":
        request = replace(request, reduce_only=False)
    elif case == "oversized_close":
        request = replace(request, quantity=D("0.5"))
    elif case == "wrong_side":
        request = replace(request, side="buy")
    else:
        request = replace(request, leverage=D(5))
    before = replay.account.snapshot()
    with pytest.raises(ValueError):
        replay.submit(
            request,
            replace(book(), source_id="next", exchange_time_ms=1500),
            ReceiptTiming(1600, 1600, 1600, False),
            maximum_book_delay_ms=50,
        )
    assert replay.account.snapshot() == before
