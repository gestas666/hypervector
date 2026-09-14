"""Declared stop scenarios through the real native adapter and offline SDK ports."""

from dataclasses import replace
from decimal import Decimal

import pytest
from test_native_replay_adapter import ADDRESS, deny_external_ports
from test_native_replay_sdk import SYMBOL, adapter, sdk
from test_native_replay_sdk_receipts import proportional_test_collateral

from hypervector.research.native_replay_depth import ExactLevel, RecordedBook
from hypervector.research.native_replay_sdk import ReplaySdk

__all__ = ["deny_external_ports"]
D = Decimal
ENTRY_ID, STOP_ID, CLOSE_ID = ("0x" + digit * 32 for digit in ("1", "2", "3"))


def protected(side: str = "long") -> tuple[ReplaySdk, int]:
    """Open five units and place a native stop; all inputs are explicitly synthetic."""
    replay = sdk()
    client = adapter(replay)
    client.configure_isolated_leverage(10)
    client.submit_entry(
        side=side, requested_notional_usd=500, mark_price=100, client_order_id=ENTRY_ID
    )
    stop = client.place_protective_stop(
        position_size_signed=5 if side == "long" else -5,
        trigger_price=98 if side == "long" else 102,
        client_order_id=STOP_ID,
    )
    replay.advance_to(2000)
    return replay, stop.oid


def cross(replay: ReplaySdk, oid: int, *, mark: Decimal, limit: Decimal) -> None:
    """Declare the exact mark observation and a separately specified transformed limit."""
    replay.observe_prices(SYMBOL, source_time_ms=replay.clock.now_ms, mark=mark, mid=mark)
    replay.protective.activate_stop(oid, mark_time_ms=replay.clock.now_ms, execution_limit=limit)


def depth(replay: ReplaySdk, quantity: Decimal = D(5)) -> RecordedBook:
    """Supply finite depth adverse to the long stop's original trigger."""
    return RecordedBook(
        f"synthetic:stop:{replay.clock.now_ms}",
        SYMBOL,
        replay.clock.now_ms,
        D(".001"),
        (ExactLevel(D("97.9"), quantity),),
        (ExactLevel(D("102.1"), quantity),),
    )


@pytest.mark.parametrize(
    "side,mark,limit,fill_px", [("long", "98", "88.2", "97.9"), ("short", "102", "112.2", "102.1")]
)
def test_stop_market_transforms_and_closes_beyond_trigger(
    side: str, mark: str, limit: str, fill_px: str
) -> None:
    """Stop identity, adverse fills, fees and delayed transformed receipts stay consistent."""
    replay, oid = protected(side)
    original = replay.orders[oid]
    cross(replay, oid, mark=D(mark), limit=D(limit))
    fills = replay.protective.match_stop(oid, depth(replay))
    assert len(fills) == 1 and fills[0].price == D(fill_px)
    assert not replay.account.snapshot().positions and not replay.collateral
    assert fills[0].order_id == str(oid) and fills[0].reduce_only
    stale = replay.info.query_order_by_oid(ADDRESS, oid)["order"]
    assert stale["status"] == "open" and stale["order"]["isTrigger"]
    assert stale["order"]["limitPx"] == str(original.limit_price)
    assert len(replay.info.user_fills(ADDRESS)) == 1
    replay.advance_to(2400)
    result = replay.info.query_order_by_oid(ADDRESS, oid)["order"]
    assert result["status"] == "filled"
    assert not result["order"]["isTrigger"] and D(result["order"]["triggerPx"]) == 0
    assert result["order"]["orderType"] == "Stop Market" and result["order"]["tif"] == "Gtc"
    assert result["order"]["limitPx"] == limit and D(result["order"]["sz"]) == 0
    assert len(replay.info.user_fills(ADDRESS)) == 2
    assert replay.fill_rows[-1][1]["crossed"] is True
    assert adapter(replay).order_status(oid).status == "filled"


def test_midpoint_crossing_cannot_activate_an_uncrossed_mark_stop() -> None:
    """A quote crossing does not substitute for the venue's mark-price trigger."""
    replay, oid = protected()
    replay.observe_prices(SYMBOL, source_time_ms=2000, mark=D(99), mid=D(97))
    before = replay.account.snapshot()
    with pytest.raises(ValueError, match="mark has not crossed"):
        replay.protective.activate_stop(oid, mark_time_ms=2000, execution_limit=D(88))
    assert replay.account.snapshot() == before and replay.orders[oid].trigger_price == 98


def test_trigger_rejects_wrong_observation_clock() -> None:
    """A declared trigger cannot cite a different mark observation than the available one."""
    replay, oid = protected()
    replay.observe_prices(SYMBOL, source_time_ms=2000, mark=D(98), mid=None)
    with pytest.raises(ValueError, match="mark observation"):
        replay.protective.activate_stop(oid, mark_time_ms=1999, execution_limit=D(88))


def test_partial_stop_stays_gtc_and_does_not_invent_a_second_queue_fill() -> None:
    """Finite depth leaves real exposure and an open transformed remainder."""
    replay, oid = protected()
    replay.partial_collateral = proportional_test_collateral
    cross(replay, oid, mark=D(98), limit=D("88.2"))
    replay.protective.match_stop(oid, depth(replay, D(2)))
    assert replay.account.snapshot().positions[SYMBOL].quantity_signed == 3
    assert replay.orders[oid].remaining == 3 and replay.orders[oid].status == "open"
    replay.advance_to(2500)
    before = replay.account.snapshot()
    with pytest.raises(ValueError, match="queue evidence"):
        replay.protective.match_stop(oid, depth(replay, D(3)))
    assert replay.account.snapshot() == before
    wire = replay.info.query_order_by_oid(ADDRESS, oid)["order"]["order"]
    assert D(wire["sz"]) == 3 and wire["tif"] == "Gtc"
    adapter(replay).cancel_order(oid)
    assert D(replay.info.query_order_by_oid(ADDRESS, oid)["order"]["order"]["sz"]) == 3


def test_partial_stop_without_collateral_model_fails_before_economics_or_depth() -> None:
    """Unsupported collateral cannot leave a partially successful account mutation."""
    replay, oid = protected()
    cross(replay, oid, mark=D(98), limit=D(88))
    book = depth(replay, D(2))
    before = replay.account.snapshot()
    with pytest.raises(ValueError, match="explicit collateral scenario"):
        replay.protective.match_stop(oid, book)
    assert replay.account.snapshot() == before and replay.orders[oid].remaining == 5
    replay.partial_collateral = proportional_test_collateral
    assert sum((f.quantity for f in replay.protective.match_stop(oid, book)), D(0)) == 2


@pytest.mark.parametrize("quantity", [D(2), D(5)])
def test_stop_during_pending_close_clamps_later_ioc_to_surviving_exposure(
    quantity: Decimal,
) -> None:
    """A stop during transport latency cannot let a previously sized close flip exposure."""
    replay, oid = protected()
    replay.partial_collateral = proportional_test_collateral

    def stop_event(current: ReplaySdk) -> None:
        cross(current, oid, mark=D(98), limit=D(88))
        current.protective.match_stop(oid, depth(current, quantity))

    replay.schedule(2050, "stop-before-close-arrival", stop_event)
    adapter(replay).close_position(position_size_signed=5, mark_price=100, client_order_id=CLOSE_ID)
    assert not replay.account.snapshot().positions and not replay.collateral
    execution = replay.venue.execution(CLOSE_ID)
    assert execution.completed_match.filled_quantity == 5 - quantity
    assert execution.completed_match.unfilled_quantity == quantity
    assert (
        sum((D(row["sz"]) for _, row in replay.fill_rows if row["dir"] == "Close Long"), D(0)) == 5
    )


def test_protective_and_ioc_matching_cannot_spend_the_same_depth_twice() -> None:
    """The stop consumes the venue's existing shared pool at the exact economic clock."""
    replay, oid = protected()
    replay.partial_collateral = proportional_test_collateral
    cross(replay, oid, mark=D(98), limit=D(88))
    book = depth(replay)
    replay.venue.match_book(book, side="sell", quantity=D(3), limit_price=D(88))
    assert sum((f.quantity for f in replay.protective.match_stop(oid, book)), D(0)) == 2
    with pytest.raises(ValueError, match="liquidity identity"):
        replay.venue.match_book(
            replace(book, source_id="alias"), side="sell", quantity=D(1), limit_price=D(88)
        )


def test_stop_can_fill_before_a_cancel_request_arrives() -> None:
    """Dispatching cancellation cannot erase an intervening economic stop execution."""
    replay, oid = protected()

    def stop_event(current: ReplaySdk) -> None:
        cross(current, oid, mark=D(98), limit=D(88))
        current.protective.match_stop(oid, depth(current))

    replay.schedule(2050, "stop-during-cancel-transit", stop_event)
    result = adapter(replay).cancel_order(oid)
    assert not result.accepted
    assert replay.orders[oid].status == "filled" and not replay.account.snapshot().positions
    assert replay.fill_rows[-1][1]["oid"] == oid


def test_protective_order_does_not_exist_before_request_arrival() -> None:
    """An engine's submission interval must not count as already established venue protection."""
    replay = sdk()
    client = adapter(replay)
    client.configure_isolated_leverage(10)
    client.submit_entry(
        side="long", requested_notional_usd=500, mark_price=100, client_order_id=ENTRY_ID
    )
    dispatch = replay.clock.now_ms
    observed: list[bool] = []
    replay.schedule(
        dispatch + 50,
        "stop-not-yet-arrived",
        lambda current: observed.append(
            any(row.client_id == STOP_ID for row in current.orders.values())
        ),
    )
    result = client.place_protective_stop(
        position_size_signed=5, trigger_price=98, client_order_id=STOP_ID
    )
    assert observed == [False]
    assert replay.orders[result.oid].created_ms == dispatch + replay.timing.arrival_delay_ms
