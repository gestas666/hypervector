"""Malformed or unsupported SDK scenarios must fail without invented execution."""

from copy import deepcopy
from decimal import Decimal

from hyperliquid.utils.types import Cloid
import pytest
from test_native_replay_adapter import ADDRESS, deny_external_ports
from test_native_replay_sdk import SYMBOL, adapter, sdk
from test_native_replay_sdk_receipts import ENTRY_ID

from hypervector.research.native_replay_clock import ReplayClock
from hypervector.research.native_replay_sdk import ReplaySdk

__all__ = ["deny_external_ports"]
D = Decimal
SECOND = Cloid.from_str("0x" + "c" * 32)


def configured_copy(**overrides: object) -> ReplaySdk:
    """Build invalid constructor scenarios from an otherwise complete explicit input set."""
    original = sdk()
    inputs = dict(
        clock=ReplayClock(1000),
        initial_cash=D(5000),
        symbols=original.symbols,
        metadata_by_dex=original.metadata_by_dex,
        dexes=original.dexes,
        fees=original.fees,
        maintenance=original.maintenance,
        execution_book=original.execution_book,
        timing=original.timing,
        decision_time=original.decision_time,
    )
    inputs.update(overrides)
    return ReplaySdk(**inputs)


def test_missing_maintenance_and_unresolved_effective_fees_cannot_initialize_replay() -> None:
    """A scenario cannot silently assume missing collateral terms or deployment fee modifiers."""
    with pytest.raises(ValueError, match="maintenance"):
        configured_copy(maintenance={})
    metadata = deepcopy(sdk().metadata_by_dex)
    del metadata["xyz"]["universe"][0]["growthMode"]
    with pytest.raises(ValueError, match="resolved effective fees"):
        configured_copy(metadata_by_dex=metadata)


def test_causal_quote_contracts_preserve_state_on_invalid_or_identical_input() -> None:
    """Future and unknown quotes fail; an exact repeated price observation is idempotent."""
    replay = sdk()
    before = replay.account.snapshot()
    replay.observe_prices(SYMBOL, source_time_ms=1000, mark=D(100), mid=D(100))
    assert replay.account.snapshot() == before
    for symbol, timestamp in ((SYMBOL, 1001), ("BTC", 1000)):
        with pytest.raises(ValueError):
            replay.observe_prices(symbol, source_time_ms=timestamp, mark=D(101), mid=D(101))
    payload = {
        "coin": SYMBOL,
        "time": 1001,
        "levels": [[{"px": "99.9", "sz": "1", "n": 1}], [{"px": "100.1", "sz": "1", "n": 1}]],
    }
    with pytest.raises(ValueError, match="future"):
        replay.observe_book(SYMBOL, payload)
    payload.update(coin="BTC", time=1000)
    with pytest.raises(ValueError, match="unknown"):
        replay.observe_book("BTC", payload)
    with pytest.raises(ValueError, match="no observed"):
        replay.info.l2_snapshot(SYMBOL)
    assert replay.account.snapshot() == before


@pytest.mark.parametrize("leverage,cross", [(0, False), (11, False), (True, False), (1, True)])
def test_invalid_leverage_does_not_alter_declared_account_mode(leverage: int, cross: bool) -> None:
    """Unsupported cross mode and malformed/out-of-spec leverage are explicit input failures."""
    replay = sdk()
    with pytest.raises(ValueError, match="isolated leverage"):
        replay.exchange.update_leverage(leverage, SYMBOL, is_cross=cross)
    assert not replay.leverage


@pytest.mark.parametrize(
    "kwargs", [dict(px=None), dict(is_buy=1), dict(cloid=None), dict(builder={"fee": 1})]
)
def test_malformed_market_request_has_no_position_or_order_side_effect(
    kwargs: dict[str, object],
) -> None:
    """Missing reference, side or identity and unmodeled builder fees cannot execute."""
    replay = sdk()
    replay.exchange.update_leverage(10, SYMBOL, is_cross=False)
    request = dict(name=SYMBOL, is_buy=True, sz=5, px=100, slippage=0.01, cloid=SECOND)
    request.update(kwargs)
    with pytest.raises(ValueError):
        replay.exchange.market_open(**request)
    assert not replay.account.snapshot().positions and not replay.orders


def test_unconfigured_leverage_close_and_batch_paths_do_not_fabricate_success() -> None:
    """Each unsupported mutation returns an explicit failure without constructing a client."""
    replay = sdk()
    with pytest.raises(ValueError, match="not configured"):
        replay.exchange.market_open(SYMBOL, True, 5, px=100, cloid=SECOND)
    with pytest.raises(ValueError, match="open exposure"):
        replay.exchange.market_close(SYMBOL, sz=5, px=100, cloid=SECOND)
    with pytest.raises(ValueError, match="queue model"):
        replay.exchange.bulk_orders([])
    assert "error" in replay.exchange.cancel(SYMBOL, 999)["response"]["data"]["statuses"][0]
    assert replay.info.user_role(ADDRESS) == {"role": "user"}
    with pytest.raises(ValueError, match="start"):
        replay.info.user_funding_history(ADDRESS, 2000, 1000)


@pytest.mark.parametrize(
    "change",
    [
        dict(reduce_only=False),
        dict(is_buy=True),
        dict(sz=6),
        dict(sz=0.0001),
        dict(order_type={"trigger": {"isMarket": False, "tpsl": "sl", "triggerPx": 98}}),
    ],
)
def test_invalid_protection_cannot_add_an_owned_order(change: dict[str, object]) -> None:
    """Wrong-side, oversized, off-grid and unsupported stop orders cannot appear as protection."""
    replay = sdk()
    client = adapter(replay)
    client.configure_isolated_leverage(10)
    client.submit_entry(
        side="long", requested_notional_usd=500, mark_price=100, client_order_id=ENTRY_ID
    )
    request = dict(
        name=SYMBOL,
        is_buy=False,
        sz=5,
        limit_px=97,
        reduce_only=True,
        cloid=SECOND,
        order_type={"trigger": {"isMarket": True, "tpsl": "sl", "triggerPx": 98}},
    )
    request.update(change)
    before = replay.account.snapshot()
    with pytest.raises(ValueError):
        replay.exchange.order(**request)
    assert len(replay.orders) == 1 and replay.account.snapshot() == before
    with pytest.raises(ValueError, match="open exposure"):
        replay.exchange.update_leverage(5, SYMBOL, is_cross=False)


def test_funding_replay_identity_is_idempotent_and_conflicts_do_not_change_cash() -> None:
    """Late duplicate observation cannot pay the same funding settlement twice."""
    replay = sdk()
    client = adapter(replay)
    client.configure_isolated_leverage(10)
    client.submit_entry(
        side="long", requested_notional_usd=500, mark_price=100, client_order_id=ENTRY_ID
    )
    args = dict(
        rate=D(".0001"),
        oracle_price=D(101),
        effective_time_ms=replay.clock.now_ms,
        visible_delay_ms=100,
    )
    replay.settle_funding("funding", SYMBOL, **args)
    expected = replay.account.snapshot()
    replay.advance_to(replay.clock.now_ms + 200)
    replay.settle_funding("funding", SYMBOL, **args)
    assert replay.account.snapshot() == expected and len(replay.funding_rows) == 1
    with pytest.raises(ValueError, match="conflicting"):
        replay.settle_funding("funding", SYMBOL, **{**args, "rate": D(".0002")})
    with pytest.raises(ValueError, match="economic clock"):
        replay.settle_funding("different", SYMBOL, **args)
