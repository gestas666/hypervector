"""Economic events inside native SDK waits must use the exposure at that event clock."""

from decimal import Decimal

import pytest
from hyperliquid.utils.types import Cloid
from test_native_replay_adapter import deny_external_ports
from test_native_replay_sdk import sdk

from hypervector.research.native_replay_sdk import ReplaySdk

__all__ = ["deny_external_ports"]
D = Decimal


def _fund(replay: ReplaySdk) -> None:
    replay.settle_funding(
        f"settlement:{replay.clock.now_ms}",
        "xyz:SNDK",
        rate=D(".001"),
        oracle_price=D(101),
        effective_time_ms=replay.clock.now_ms,
        visible_delay_ms=0,
    )


@pytest.mark.parametrize("offset,expected", [(50, "0"), (150, "-.101")])
def test_funding_inside_entry_latency_uses_exact_economic_exposure(
    offset: int,
    expected: str,
) -> None:
    """Pre-fill funding is flat; post-fill funding applies before the entry response."""
    replay = sdk()
    replay.exchange.update_leverage(3, "xyz:SNDK", is_cross=False)
    replay.schedule(replay.clock.now_ms + offset, f"fund:{offset}", _fund)
    replay.exchange.market_open("xyz:SNDK", True, 1, 100, 0.01, Cloid.from_int(1))
    assert replay.account.snapshot().funding_usd == D(expected)
    assert len(replay.funding_rows) == (1 if offset > 100 else 0)


def test_funding_inside_close_response_does_not_charge_already_flat_account() -> None:
    """The native close fill precedes subsequent funding even when receipts remain pending."""
    replay = sdk()
    replay.exchange.update_leverage(3, "xyz:SNDK", is_cross=False)
    replay.exchange.market_open("xyz:SNDK", True, 1, 100, 0.01, Cloid.from_int(1))
    replay.schedule(replay.clock.now_ms + 50, "before-close", _fund)
    replay.schedule(replay.clock.now_ms + 150, "after-close", _fund)
    replay.exchange.market_close("xyz:SNDK", 1, 100, 0.01, Cloid.from_int(2))
    assert replay.account.snapshot().funding_usd == D("-.101")
    assert len(replay.funding_rows) == 1 and not replay.account.snapshot().positions


def test_runtime_clock_waits_apply_events_in_stable_order() -> None:
    """The same clock facade used by acquisition and recovery dispatches intermediate events."""
    replay = sdk()
    seen: list[tuple[int, str]] = []
    replay.schedule(1050, "first", lambda r: seen.append((r.clock.now_ms, "first")))
    replay.schedule(1050, "second", lambda r: seen.append((r.clock.now_ms, "second")))
    replay.runtime_clock.sleep(0.1)
    assert seen == [(1050, "first"), (1050, "second")]
    assert replay.clock.now_ms == replay.runtime_clock.now_ms == 1100
    replay.runtime_clock.advance_to(1200)
    assert replay.runtime_clock.monotonic() == 0.2
    assert replay.runtime_clock.now() == replay.clock.now()
