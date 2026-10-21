"""Offline tests for BTC post-only source-follow venue execution."""

from collections.abc import Mapping

import pytest
from requests import Timeout

from hypervector.live.hyperliquid_btc_adapter import BtcHyperliquidAdapter
from hypervector.live.hyperliquid_protocol import HyperliquidPostOnlyOrder
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError
from hypervector.live.sol_order_transport import HyperliquidBatchOrderTransportError

_ADDRESS = "0x1111111111111111111111111111111111111111"
_CLOID = "0x0123456789abcdef0123456789abcdef"


class _Info:
    def __init__(self) -> None:
        self.account_mode_calls = 0

    def meta(self, dex: str = "") -> object:
        return {"universe": [{"name": "BTC", "szDecimals": 5, "maxLeverage": 40}]}

    def user_fees(self, address: str) -> object:
        return {
            "userAddRate": "0.00015",
            "userCrossRate": "0.00045",
            "activeReferralDiscount": "0",
        }

    def all_mids(self, dex: str = "") -> object:
        return {"BTC": "64000.0"}

    def l2_snapshot(self, name: str) -> object:
        return {
            "coin": "BTC",
            "time": 1_785_513_900_000,
            "levels": [
                [{"px": "63999", "sz": "1.0", "n": 2}],
                [{"px": "64001", "sz": "0.9", "n": 2}],
            ],
        }

    def user_state(self, address: str, dex: str = "") -> object:
        return {
            "assetPositions": [
                {
                    "position": {
                        "coin": "BTC",
                        "szi": "-0.025",
                        "entryPx": "64001",
                        "liquidationPx": "66010",
                        "marginUsed": "53.34",
                        "positionValue": "1600.025",
                        "unrealizedPnl": "0",
                        "leverage": {"type": "isolated", "value": 30},
                    }
                }
            ],
            "marginSummary": {
                "accountValue": "153.61",
                "totalMarginUsed": "53.34",
                "totalNtlPos": "1600.025",
            },
            "withdrawable": "100.27",
        }

    def query_user_abstraction_state(self, address: str) -> object:
        self.account_mode_calls += 1
        return "disabled"

    def spot_user_state(self, address: str) -> object:
        return {"balances": []}

    def frontend_open_orders(self, address: str, dex: str = "") -> object:
        return []

    def user_fills(self, address: str) -> object:
        return []

    def query_order_by_oid(self, user: str, oid: int | str) -> object:
        return {
            "status": "order",
            "order": {
                "order": {"coin": "BTC", "oid": oid, "sz": "0.025"},
                "status": "open",
                "statusTimestamp": 1_785_513_900_000,
            },
        }

    def user_funding_history(
        self,
        user: str,
        startTime: int,
        endTime: int | None = None,
    ) -> object:
        return []


class _Exchange:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, object]]] = []
        self.bulk_statuses: list[object] = [
            {"resting": {"oid": 201}},
            {"resting": {"oid": 202}},
        ]
        self.bulk_transport_failure = False

    def update_leverage(
        self, leverage: int, name: str, is_cross: bool = True
    ) -> object:
        self.calls.append(
            ("leverage", {"value": leverage, "name": name, "cross": is_cross})
        )
        return {"status": "ok", "response": {"type": "default"}}

    def order(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        order_type: object,
        reduce_only: bool = False,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        self.calls.append(
            (
                "order",
                {
                    "name": name,
                    "is_buy": is_buy,
                    "size": sz,
                    "price": limit_px,
                    "order_type": order_type,
                    "reduce_only": reduce_only,
                },
            )
        )
        return {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"resting": {"oid": 101}}]},
            },
        }

    def bulk_orders(
        self,
        order_requests: list[object],
        builder: object | None = None,
        grouping: str = "na",
    ) -> object:
        self.calls.append(
            (
                "bulk_orders",
                {
                    "orders": order_requests,
                    "builder": builder,
                    "grouping": grouping,
                },
            )
        )
        if self.bulk_transport_failure:
            raise Timeout("injected response loss")
        return {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": self.bulk_statuses},
            },
        }

    def cancel(self, name: str, oid: int) -> object:
        return {
            "status": "ok",
            "response": {"type": "cancel", "data": {"statuses": ["success"]}},
        }

    def market_open(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        px: float | None = None,
        slippage: float = 0.05,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        self.calls.append(
            (
                "market_open",
                {
                    "name": name,
                    "is_buy": is_buy,
                    "size": sz,
                    "price": px,
                    "slippage": slippage,
                },
            )
        )
        return {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"filled": {"oid": 102, "totalSz": str(sz)}}]},
            },
        }

    def market_close(
        self,
        coin: str,
        sz: float | None = None,
        px: float | None = None,
        slippage: float = 0.05,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        self.calls.append(
            (
                "market_close",
                {
                    "name": coin,
                    "size": sz,
                    "price": px,
                    "slippage": slippage,
                },
            )
        )
        return {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"filled": {"oid": 103, "totalSz": sz}}]},
            },
        }


def _adapter() -> tuple[BtcHyperliquidAdapter, _Exchange]:
    exchange = _Exchange()
    return (
        BtcHyperliquidAdapter(
            info=_Info(),
            exchange=exchange,
            account_address=_ADDRESS,
            max_notional_usd=1_700.0,
            slippage_fraction=0.01,
        ),
        exchange,
    )


def test_preflight_reads_btc_isolated_account_state() -> None:
    """BTC metadata and position data must not leak through SOL filtering."""
    adapter, _ = _adapter()

    preflight = adapter.preflight(expected_max_leverage=40)

    assert preflight.market.symbol == "BTC"
    assert preflight.market.size_decimals == 5
    assert preflight.position.size_signed == pytest.approx(-0.025)
    assert preflight.position.leverage_type == "isolated"
    assert preflight.position.leverage == 30
    assert preflight.position.liquidation_price == pytest.approx(66_010.0)


def test_preflight_caches_stable_account_mode_for_reconciliation() -> None:
    """A live loop must not spend a high-weight mode lookup every cycle."""
    info = _Info()
    adapter = BtcHyperliquidAdapter(
        info=info,
        exchange=_Exchange(),
        account_address=_ADDRESS,
        max_notional_usd=1_700.0,
        slippage_fraction=0.01,
    )

    adapter.preflight(expected_max_leverage=40)
    adapter.reconcile()
    adapter.reconcile()

    assert info.account_mode_calls == 1


def test_hip3_adapter_preserves_namespace_across_reads_and_mutations() -> None:
    """Every namespaced read and order must retain the exact HIP-3 identity."""

    class Hip3Info(_Info):
        def __init__(self) -> None:
            super().__init__()
            self.dex_calls: list[tuple[str, str]] = []

        def meta(self, dex: str = "") -> object:
            self.dex_calls.append(("meta", dex))
            return {
                "collateralToken": 0,
                "universe": [
                    {
                        "name": "xyz:AAA",
                        "szDecimals": 3,
                        "maxLeverage": 50,
                        "growthMode": "disabled",
                    }
                ],
            }

        def perp_dexs(self) -> object:
            self.dex_calls.append(("perp_dexs", "xyz"))
            return [{"name": "xyz", "deployerFeeScale": "1.0"}]

        def all_mids(self, dex: str = "") -> object:
            self.dex_calls.append(("all_mids", dex))
            return {"xyz:AAA": "7750.0"}

        def user_state(self, address: str, dex: str = "") -> object:
            self.dex_calls.append(("user_state", dex))
            state = super().user_state(address, dex)
            state["assetPositions"] = []
            return state

        def frontend_open_orders(self, address: str, dex: str = "") -> object:
            self.dex_calls.append(("open_orders", dex))
            return []

    info = Hip3Info()
    exchange = _Exchange()
    adapter = BtcHyperliquidAdapter(
        info=info,
        exchange=exchange,
        account_address=_ADDRESS,
        max_notional_usd=75.0,
        slippage_fraction=0.01,
        symbol="xyz:AAA",
        perp_dex="xyz",
    )

    preflight = adapter.preflight(expected_max_leverage=50)
    adapter.configure_isolated_leverage(5)
    entry = adapter.submit_market_entry(
        side="long",
        requested_notional_usd=25.0,
        mark_price=7_750.0,
        client_order_id=_CLOID,
    )
    stop = adapter.place_protective_stop(
        position_size_signed=0.003,
        trigger_price=7_700.0,
        client_order_id=_CLOID,
    )
    close = adapter.close_position(
        position_size_signed=0.003,
        mark_price=7_760.0,
        client_order_id=_CLOID,
    )
    adapter.reconcile()

    assert adapter.symbol == "xyz:AAA"
    assert adapter.perp_dex == "xyz"
    assert preflight.market.max_leverage == 50
    assert entry.accepted and stop.accepted and close.accepted
    assert {dex for _, dex in info.dex_calls} == {"xyz"}
    assert [payload["name"] for _, payload in exchange.calls] == [
        "xyz:AAA",
        "xyz:AAA",
        "xyz:AAA",
        "xyz:AAA",
    ]


def test_entry_and_target_are_btc_post_only_limit_orders() -> None:
    """The live adapter must preserve maker entry and reduce-only target semantics."""
    adapter, exchange = _adapter()
    adapter.configure_isolated_leverage(30)

    entry = adapter.submit_entry(
        side="short",
        requested_notional_usd=1_600.0,
        limit_price=64_001.0,
        client_order_id=_CLOID,
    )
    target = adapter.submit_target(
        position_size_signed=-0.02499,
        limit_price=63_830.0,
        client_order_id=_CLOID,
    )

    assert entry.accepted and target.accepted
    assert exchange.calls[0] == (
        "leverage",
        {"value": 30, "name": "BTC", "cross": False},
    )
    entry_call = exchange.calls[1][1]
    assert entry_call["name"] == "BTC"
    assert entry_call["is_buy"] is False
    assert entry_call["size"] == pytest.approx(0.02499)
    assert entry_call["order_type"] == {"limit": {"tif": "Alo"}}
    assert entry_call["reduce_only"] is False
    target_call = exchange.calls[2][1]
    assert target_call["is_buy"] is True
    assert target_call["reduce_only"] is True
    assert target_call["order_type"] == {"limit": {"tif": "Alo"}}


def test_quote_pair_uses_one_batched_sdk_order_action() -> None:
    """Both maker legs must be signed and posted in one venue request."""
    adapter, exchange = _adapter()
    requests = (
        HyperliquidPostOnlyOrder(
            side="buy",
            requested_notional_usd=12.5,
            limit_price=63_999.0,
            client_order_id="0x00000000000000000000000000000001",
        ),
        HyperliquidPostOnlyOrder(
            side="sell",
            requested_notional_usd=12.5,
            limit_price=64_001.0,
            client_order_id="0x00000000000000000000000000000002",
        ),
    )

    acknowledgements = adapter.submit_post_only_batch(requests)

    assert [ack.oid for ack in acknowledgements] == [201, 202]
    assert [ack.client_order_id for ack in acknowledgements] == [
        requests[0].client_order_id,
        requests[1].client_order_id,
    ]
    assert [name for name, _ in exchange.calls] == ["bulk_orders"]
    payload = exchange.calls[0][1]
    orders = payload["orders"]
    assert isinstance(orders, list)
    assert [order["is_buy"] for order in orders] == [True, False]
    assert all(order["order_type"] == {"limit": {"tif": "Alo"}} for order in orders)
    assert all(order["reduce_only"] is False for order in orders)


def test_quote_batch_preserves_ordered_partial_rejection() -> None:
    """One rejected batch leg must not hide the accepted partner identity."""
    adapter, exchange = _adapter()
    exchange.bulk_statuses = [
        {"resting": {"oid": 201}},
        {"error": "Post only order would have immediately matched"},
    ]
    requests = (
        HyperliquidPostOnlyOrder("buy", 12.5, 63_999.0, "0x" + "1" * 32),
        HyperliquidPostOnlyOrder("sell", 12.5, 64_001.0, "0x" + "2" * 32),
    )

    acknowledgements = adapter.submit_post_only_batch(requests)

    assert acknowledgements[0].accepted and acknowledgements[0].oid == 201
    assert not acknowledgements[1].accepted
    assert "immediately matched" in (acknowledgements[1].error or "")


def test_quote_batch_transport_error_preserves_both_client_ids() -> None:
    """A lost batch response must expose both identities for exact recovery."""
    adapter, exchange = _adapter()
    exchange.bulk_transport_failure = True
    requests = (
        HyperliquidPostOnlyOrder("buy", 12.5, 63_999.0, "0x" + "1" * 32),
        HyperliquidPostOnlyOrder("sell", 12.5, 64_001.0, "0x" + "2" * 32),
    )

    with pytest.raises(HyperliquidBatchOrderTransportError) as raised:
        adapter.submit_post_only_batch(requests)

    assert raised.value.client_order_ids == tuple(
        request.client_order_id for request in requests
    )


def test_long_entry_and_target_use_opposite_post_only_sides() -> None:
    """A long opens with a maker buy and closes with a reduce-only maker sell."""
    adapter, exchange = _adapter()

    entry = adapter.submit_entry(
        side="long",
        requested_notional_usd=1_600.0,
        limit_price=63_999.0,
        client_order_id=_CLOID,
    )
    target = adapter.submit_target(
        position_size_signed=0.025,
        limit_price=64_169.0,
        client_order_id=_CLOID,
    )

    assert entry.accepted and target.accepted
    entry_call = exchange.calls[0][1]
    assert entry_call["is_buy"] is True
    assert entry_call["reduce_only"] is False
    target_call = exchange.calls[1][1]
    assert target_call["is_buy"] is False
    assert target_call["reduce_only"] is True


def test_entry_notional_cannot_exceed_explicit_canary_cap() -> None:
    """A later account balance cannot silently enlarge this canary order."""
    adapter, _ = _adapter()

    with pytest.raises(HyperliquidAdapterError, match="exceeds cap 1700"):
        adapter.submit_entry(
            side="short",
            requested_notional_usd=1_700.01,
            limit_price=64_001.0,
            client_order_id=_CLOID,
        )


def test_hulk_market_entry_and_native_stop_are_explicit_btc_orders() -> None:
    """The Hulk path needs a bounded market entry and venue-native protection."""
    adapter, exchange = _adapter()

    entry = adapter.submit_market_entry(
        side="short",
        requested_notional_usd=150.0,
        mark_price=64_000.0,
        client_order_id=_CLOID,
    )
    stop = adapter.place_protective_stop(
        position_size_signed=-0.00234,
        trigger_price=64_100.0,
        client_order_id=_CLOID,
    )

    assert entry.accepted and stop.accepted
    entry_call = exchange.calls[0][1]
    assert entry_call == {
        "name": "BTC",
        "is_buy": False,
        "size": pytest.approx(0.00234),
        "price": 64_000.0,
        "slippage": 0.01,
    }
    stop_call = exchange.calls[1][1]
    assert stop_call["name"] == "BTC"
    assert stop_call["is_buy"] is True
    assert stop_call["size"] == pytest.approx(0.00234)
    assert stop_call["price"] == 64_100.0
    assert stop_call["reduce_only"] is True
    assert stop_call["order_type"] == {
        "trigger": {"triggerPx": 64_100.0, "isMarket": True, "tpsl": "sl"}
    }


def test_hardened_ioc_cap_reaches_both_entry_and_forced_close() -> None:
    """The hardened BTC cap must protect both SDK market mutation paths."""
    exchange = _Exchange()
    adapter = BtcHyperliquidAdapter(
        info=_Info(),
        exchange=exchange,
        account_address=_ADDRESS,
        max_notional_usd=1_700.0,
        slippage_fraction=0.002,
    )

    entry = adapter.submit_market_entry(
        side="long",
        requested_notional_usd=150.0,
        mark_price=64_000.0,
        client_order_id=_CLOID,
    )
    close = adapter.close_position(
        position_size_signed=0.00234,
        mark_price=64_020.0,
        client_order_id="0x00000000000000000000000000000002",
    )

    assert entry.accepted and close.accepted
    assert exchange.calls[0][0] == "market_open"
    assert exchange.calls[0][1]["slippage"] == pytest.approx(0.002)
    assert exchange.calls[1][0] == "market_close"
    assert exchange.calls[1][1]["slippage"] == pytest.approx(0.002)
