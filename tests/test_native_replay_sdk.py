"""Native adapters must consume the reusable offline SDK ports without mocks."""

from decimal import Decimal

import pytest
from test_native_replay_adapter import ADDRESS, deny_external_ports

from hypervector.live.hyperliquid_btc_adapter import BtcHyperliquidAdapter
from hypervector.live.multi_asset_directional_adapter import MultiAssetDirectionalAdapter
from hypervector.research.native_replay_clock import ReplayClock
from hypervector.research.native_replay_depth import ExactLevel, RecordedBook
from hypervector.research.native_replay_sdk import ReplaySdk, ReplaySdkTiming
from hypervector.research.native_replay_unified import MaintenanceTier

__all__ = ["deny_external_ports"]
D = Decimal
SYMBOL = "xyz:CCC"


def sdk() -> ReplaySdk:
    """Declare complete synthetic source inputs; no signing or HTTP client exists."""
    clock = ReplayClock(1000)
    result = ReplaySdk(
        clock=clock,
        initial_cash=D(5000),
        symbols=(SYMBOL,),
        metadata_by_dex={
            "xyz": {
                "collateralToken": 0,
                "universe": [
                    {
                        "name": SYMBOL,
                        "szDecimals": 3,
                        "maxLeverage": 10,
                        "growthMode": "enabled",
                        "deployerFeeScale": "1",
                    }
                ],
            }
        },
        dexes=[None, {"name": "xyz"}],
        fees={"userAddRate": ".00015", "userCrossRate": ".0009", "activeReferralDiscount": "0"},
        maintenance={SYMBOL: (MaintenanceTier(D(0), D(".05"), D(0)),)},
        execution_book=recorded_book,
        timing=ReplaySdkTiming(100, 200, 300, 400, 50),
        decision_time=lambda symbol, reduce: clock.now_ms,
    )
    result.observe_prices(SYMBOL, source_time_ms=1000, mark=D(100), mid=D(100))
    return result


def recorded_book(symbol: str, arrival_ms: int, step: Decimal) -> RecordedBook:
    """Supply finite scenario depth at its exact declared exchange clock."""
    return RecordedBook(
        f"synthetic:{symbol}:{arrival_ms}",
        symbol,
        arrival_ms,
        step,
        (ExactLevel(D("99.9"), D(100)),),
        (ExactLevel(D("100.1"), D(100)),),
    )


def adapter(replay: ReplaySdk) -> MultiAssetDirectionalAdapter:
    """Use the real directional and SDK adapters around one offline shared state."""
    return MultiAssetDirectionalAdapter(
        BtcHyperliquidAdapter(
            info=replay.info,
            exchange=replay.exchange,
            account_address=ADDRESS,
            max_notional_usd=500,
            slippage_fraction=0.01,
            symbol=SYMBOL,
            perp_dex="xyz",
        )
    )


@pytest.mark.parametrize("side", ["long", "short"])
def test_native_adapter_full_lifecycle_uses_shared_sdk_order_namespace(side: str) -> None:
    """Entry, protection, target, funding, close and cleanup reconcile to one exact account."""
    replay, client = sdk(), None
    client = adapter(replay)
    preflight = client.preflight(expected_max_leverage=10)
    assert preflight.account_value_usd == 5000
    client.configure_isolated_leverage(10)
    entry = client.submit_entry(
        side=side, requested_notional_usd=500, mark_price=100, client_order_id="0x" + "1" * 32
    )
    replay.advance_to(replay.clock.now_ms + 500)
    position = client.reconcile().position
    assert abs(position.size_signed) == 5 and entry.oid == 1
    stop = client.place_protective_stop(
        position_size_signed=position.size_signed,
        trigger_price=98 if side == "long" else 102,
        client_order_id="0x" + "2" * 32,
    )
    target = client.submit_target(
        position_size_signed=position.size_signed,
        limit_price=102 if side == "long" else 98,
        client_order_id="0x" + "3" * 32,
    )
    replay.advance_to(replay.clock.now_ms + 500)
    assert {o.oid for o in client.reconcile().open_orders} == {2, 3}
    replay.settle_funding(
        "hour-1",
        SYMBOL,
        rate=D(".0001"),
        oracle_price=D(101),
        effective_time_ms=replay.clock.now_ms,
        visible_delay_ms=100,
    )
    replay.advance_to(replay.clock.now_ms + 100)
    payments = client.funding_payments(start_time_ms=1000, end_time_ms=replay.clock.now_ms)
    assert len(payments) == 1 and payments[0].usdc_delta == (-0.0505 if side == "long" else 0.0505)
    closed = client.close_position(
        position_size_signed=position.size_signed, mark_price=100, client_order_id="0x" + "4" * 32
    )
    replay.advance_to(replay.clock.now_ms + 500)
    assert closed.oid == 4 and client.reconcile().position.size_signed == 0
    assert client.cancel_order(stop.oid).accepted and client.cancel_order(target.oid).accepted
    replay.advance_to(replay.clock.now_ms + 500)
    observed, exact = client.reconcile(), replay.account.snapshot()
    assert observed.is_flat and len(observed.fills) == 2
    assert observed.account.account_value_usd == pytest.approx(float(exact.equity_usd))
    assert {f.oid for f in observed.fills} == {1, 4}
    assert client.order_status(entry.oid).status == "filled"
    assert client.order_status(stop.oid).status == "canceled"


def test_sdk_readers_do_not_leak_mutable_order_or_account_storage() -> None:
    """Consumer edits to SDK-shaped responses cannot alter later account reconciliation."""
    replay = sdk()
    state = replay.info.spot_user_state(ADDRESS)
    state["balances"][0]["total"] = "0"
    assert replay.info.spot_user_state(ADDRESS)["balances"][0]["total"] == "5000"
    metadata = replay.info.meta("xyz")
    metadata["universe"][0]["szDecimals"] = 1
    assert replay.info.meta("xyz")["universe"][0]["szDecimals"] == 3
