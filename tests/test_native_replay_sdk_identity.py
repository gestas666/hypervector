"""One replay order namespace must cover IOC and protective SDK receipts."""

from dataclasses import replace

import pytest
from test_native_replay_depth import book
from test_native_replay_venue import D, order, timing, venue

from hypervector.research.native_replay_venue import RecordedIocVenue


def test_sdk_order_allocator_preserves_identity_in_account_ack_and_fills() -> None:
    """An external order namespace remains exact across all native account receipts."""
    base = venue()
    ids = iter((41, 43))
    replay = RecordedIocVenue(base.account, base.clock, oid_allocator=lambda: next(ids))
    replay.submit(order(), book(), timing(), maximum_book_delay_ms=50)
    detached = replay.execution("order:1")
    assert detached.oid == 41 and not detached.applied and not detached.fills
    detached.applied = True
    assert not replay.execution("order:1").applied
    replay.advance_to(1400)
    view = replay.execution("order:1")
    assert view.applied and {fill.order_id for fill in view.fills} == {"41"}
    assert replay.account.snapshot().positions["xyz:SNDK"].opening_order_id == "41"
    assert replay.response("order:1")["response"]["data"]["statuses"][0]["filled"]["oid"] == 41
    replay.submit(order(), book(), timing(), maximum_book_delay_ms=50)
    assert next(ids) == 43, "idempotent request replay must not allocate another order ID"


@pytest.mark.parametrize("invalid", [True, 0, -1, 1.5])
def test_malformed_allocated_order_id_cannot_mutate_liquidity_or_economics(invalid: int) -> None:
    """An invalid shared namespace fails before a book is consumed or an order is accepted."""
    base = venue()
    ids = iter((invalid, 17))
    replay = RecordedIocVenue(base.account, base.clock, oid_allocator=lambda: next(ids))
    before = base.account.snapshot()
    with pytest.raises(ValueError, match="order ID"):
        replay.submit(order(), book(), timing(), maximum_book_delay_ms=50)
    assert base.account.snapshot() == before
    replay.submit(order(), book(), timing(), maximum_book_delay_ms=50)
    replay.advance_to(1400)
    assert replay.execution("order:1").match.filled_quantity == order().quantity


def test_duplicate_shared_order_id_is_rejected_without_replacing_prior_identity() -> None:
    """A collision must not overwrite a previously accepted no-fill order."""
    base = venue()
    ids = iter((17, 17, 18))
    replay = RecordedIocVenue(base.account, base.clock, oid_allocator=lambda: next(ids))
    missed = replace(order(), limit_price=D(99))
    replay.submit(missed, book(), timing(), maximum_book_delay_ms=50)
    replay.advance_to(1400)
    followup = replace(
        order(),
        client_order_id="next",
        decision_time_ms=1400,
        dispatch_time_ms=1400,
        arrival_time_ms=1450,
    )
    source = replace(book(), source_id="later", exchange_time_ms=1500)
    receipt = replace(timing(), response_ms=1600, fill_visible_ms=1700, order_visible_ms=1800)
    with pytest.raises(ValueError, match="order ID"):
        replay.submit(followup, source, receipt, maximum_book_delay_ms=50)
    replay.submit(followup, source, receipt, maximum_book_delay_ms=50)
    replay.advance_to(1800)
    assert replay.execution("order:1").oid == 17 and not replay.execution("order:1").fills
    assert replay.execution("next").oid == 18
    assert replay.execution("next").match.filled_quantity == order().quantity
