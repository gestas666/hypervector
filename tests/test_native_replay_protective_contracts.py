"""Invalid stop sources and exhausted exposure cannot create fictional protective fills."""

from dataclasses import replace
from decimal import Decimal

import pytest
from test_native_replay_adapter import deny_external_ports
from test_native_replay_protective_execution import CLOSE_ID, cross, depth, protected
from test_native_replay_sdk import adapter

__all__ = ["deny_external_ports"]
D = Decimal


def test_orphaned_stop_cancellation_preserves_its_unfilled_requested_quantity() -> None:
    """An intervening full close leaves no exposure for an old reduce-only stop to execute."""
    replay, oid = protected()
    adapter(replay).close_position(position_size_signed=5, mark_price=100, client_order_id=CLOSE_ID)
    cross(replay, oid, mark=D(98), limit=D(88))
    before = replay.account.snapshot()
    assert replay.protective.match_stop(oid, depth(replay)) == ()
    assert replay.account.snapshot() == before
    assert replay.orders[oid].status == "canceled"
    assert replay.orders[oid].remaining == 5


def test_stop_limit_with_no_executable_depth_remains_an_unfilled_gtc_order() -> None:
    """A trigger crossing cannot promise execution at an unreachable transformed limit."""
    replay, oid = protected()
    cross(replay, oid, mark=D(98), limit=D(98))
    before = replay.account.snapshot()
    assert replay.protective.match_stop(oid, depth(replay)) == ()
    assert replay.account.snapshot() == before
    assert replay.orders[oid].status == "open" and replay.orders[oid].remaining == 5


@pytest.mark.parametrize("invalid", ["symbol", "lot", "time"])
def test_wrong_stop_source_cannot_mutate_economics_or_order_receipts(invalid: str) -> None:
    """A different market, lot grid or economic clock is a technical source error."""
    replay, oid = protected()
    cross(replay, oid, mark=D(98), limit=D(88))
    book = depth(replay)
    changes = {
        "symbol": dict(symbol="BTC"),
        "lot": dict(quantity_step=D(".01")),
        "time": dict(exchange_time_ms=replay.clock.now_ms + 1),
    }
    before, order = replay.account.snapshot(), replay.orders[oid]
    with pytest.raises(ValueError, match="stop execution book"):
        replay.protective.match_stop(oid, replace(book, **changes[invalid]))
    assert replay.account.snapshot() == before and replay.orders[oid] == order


@pytest.mark.parametrize("invalid", ["untriggered", "unknown", "canceled", "reactivated"])
def test_invalid_stop_lifecycle_cannot_acquire_an_execution(invalid: str) -> None:
    """Protective actions require original owned identity and one observed trigger event."""
    replay, oid = protected()
    if invalid == "canceled":
        adapter(replay).cancel_order(oid)
    if invalid == "reactivated":
        cross(replay, oid, mark=D(98), limit=D(88))
    before = replay.account.snapshot()
    with pytest.raises(ValueError):
        if invalid == "reactivated":
            replay.protective.activate_stop(
                oid, mark_time_ms=replay.clock.now_ms, execution_limit=D(88)
            )
        else:
            replay.protective.match_stop(999 if invalid == "unknown" else oid, depth(replay))
    assert replay.account.snapshot() == before
