"""Scheduled executions must share causal depth and recheck remaining reduce-only exposure."""

from dataclasses import replace

import pytest
from test_native_replay_depth import book
from test_native_replay_venue import D, order, timing, venue

from hypervector.research.native_replay_events import FillEvent
from hypervector.research.native_replay_venue import IocOrder, ReceiptTiming, RecordedIocVenue


def test_pending_order_has_no_predetermined_match() -> None:
    """Submission cannot expose or reserve a future economic fill."""
    replay = venue()
    replay.submit(order(), book(), timing(), maximum_book_delay_ms=50)
    assert replay.execution("order:1").match is None
    replay.advance_to(1099)
    assert replay.execution("order:1").match is None
    replay.advance_to(1100)
    assert replay.execution("order:1").match.filled_quantity == D(".25")


def test_prior_book_consumption_precedes_pending_ioc_matching() -> None:
    """Two declared executions cannot both receive the same finite recorded ask quantity."""
    replay = venue()
    replay.submit(order(), book(), timing(), maximum_book_delay_ms=50)
    replay.clock.advance_to(1100)
    first = replay.match_book(book(), side="buy", quantity=D(".15"), limit_price=D("100.2"))
    replay.advance_to(1100)
    second = replay.execution("order:1").match
    assert first.filled_quantity == second.filled_quantity == D(".15")
    assert second.requested_quantity == D(".25") and second.unfilled_quantity == D(".10")
    assert replay.account.snapshot().positions["xyz:CCC"].quantity_signed == D(".15")


@pytest.mark.parametrize("time", [1099, 1101])
def test_direct_depth_matching_requires_exact_economic_clock(time: int) -> None:
    """Neither an unseen future book nor an earlier publication can silently become a fill."""
    replay = venue()
    replay.clock.advance_to(time)
    with pytest.raises(ValueError, match="economic clock"):
        replay.match_book(book(), side="buy", quantity=D(".1"), limit_price=D("100.2"))


def _queued_close() -> tuple[RecordedIocVenue, IocOrder]:
    replay = venue()
    replay.submit(order(), book(), timing(), maximum_book_delay_ms=50)
    replay.advance_to(1400)
    closing = replace(
        order(),
        client_order_id="late-close",
        side="sell",
        limit_price=D("99.7"),
        dispatch_time_ms=1400,
        arrival_time_ms=1600,
        decision_time_ms=1400,
        reduce_only=True,
    )
    replay.submit(
        closing,
        replace(book(), source_id="close-book", exchange_time_ms=1600),
        ReceiptTiming(1700, 1700, 1700, False),
        maximum_book_delay_ms=0,
    )
    return replay, closing


@pytest.mark.parametrize("earlier_quantity", [D(".1"), D(".25")])
def test_pending_reduction_cannot_overclose_after_an_earlier_reduction(
    earlier_quantity: D,
) -> None:
    """A stop before a queued close changes its available quantity without resizing the request."""
    replay, closing = _queued_close()
    replay.clock.advance_to(1500)
    replay.account.apply_fill(
        FillEvent(
            "earlier-protection",
            "99",
            closing.symbol,
            "sell",
            earlier_quantity,
            D(99),
            D(0),
            closing.leverage,
            1400,
            1500,
            1500,
            replay.clock.next_stamp(),
            True,
        )
    )
    replay.advance_to(1700)
    execution = replay.execution(closing.client_order_id)
    assert execution.match.requested_quantity == closing.quantity == D(".25")
    assert execution.match.filled_quantity == D(".25") - earlier_quantity
    assert execution.match.unfilled_quantity == earlier_quantity
    assert not replay.account.snapshot().positions
    if earlier_quantity < D(".25"):
        assert execution.position_before.quantity_signed == D(".15")
    else:
        assert execution.position_before is None and execution.match.disposition == "no_fill"


def test_book_alias_cannot_replenish_depth_at_the_same_source_clock() -> None:
    """A second identity for the same symbol/time must not refill consumed visible liquidity."""
    replay = venue()
    replay.clock.advance_to(1100)
    replay.match_book(book(), side="buy", quantity=D(".1"), limit_price=D("100.2"))
    with pytest.raises(ValueError, match="source clock"):
        replay.match_book(
            replace(book(), source_id="alias"), side="buy", quantity=D(".1"), limit_price=D("100.2")
        )
