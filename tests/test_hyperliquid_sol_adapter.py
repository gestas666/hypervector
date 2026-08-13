"""Offline contract tests for the narrow SOL Hyperliquid venue adapter."""

from __future__ import annotations

from collections.abc import Mapping
from unittest.mock import Mock

import pytest
from requests import RequestException

from hypervector.live.hyperliquid_sol_adapter import (
    HyperliquidAdapterError,
    SolHyperliquidAdapter,
)

_CLIENT_ORDER_ID = "0x0123456789abcdef0123456789abcdef"


class FakeInfo:
    """Record read-only SDK calls and return deterministic venue payloads."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.position_size = "0.30"
        self.open_orders: list[dict[str, object]] = []

    def meta(self, dex: str = "") -> object:
        self.calls.append(("meta", dex))
        return {
            "universe": [
                {"name": "BTC", "szDecimals": 5, "maxLeverage": 40},
                {"name": "SOL", "szDecimals": 2, "maxLeverage": 20},
            ]
        }

    def user_fees(self, address: str) -> object:
        self.calls.append(("user_fees", address))
        return {
            "userAddRate": "0.00015",
            "userCrossRate": "0.00045",
            "activeReferralDiscount": "0",
        }

    def all_mids(self, dex: str = "") -> object:
        self.calls.append(("all_mids", dex))
        return {"BTC": "64000.0", "SOL": "73.673"}

    def l2_snapshot(self, name: str) -> object:
        self.calls.append(("l2_snapshot", name))
        return {
            "coin": "SOL",
            "time": 1_785_499_200_123,
            "levels": [
                [
                    {"px": "73.670", "sz": "10.0", "n": 3},
                    {"px": "73.660", "sz": "5.0", "n": 2},
                ],
                [
                    {"px": "73.680", "sz": "6.0", "n": 2},
                    {"px": "73.690", "sz": "4.0", "n": 1},
                ],
            ],
        }

    def user_state(self, address: str, dex: str = "") -> object:
        self.calls.append(("user_state", (address, dex)))
        positions: list[dict[str, object]] = []
        if float(self.position_size) != 0.0:
            positions.append(
                {
                    "type": "oneWay",
                    "position": {
                        "coin": "SOL",
                        "szi": self.position_size,
                        "entryPx": "73.10",
                        "liquidationPx": "60.50",
                        "marginUsed": "4.386",
                        "positionValue": "21.93",
                        "unrealizedPnl": "0.12",
                        "leverage": {"type": "isolated", "value": 5},
                    },
                }
            )
        return {
            "assetPositions": positions,
            "marginSummary": {
                "accountValue": "150.00",
                "totalMarginUsed": "4.386",
                "totalNtlPos": "21.93",
            },
            "withdrawable": "145.614",
        }

    def query_user_abstraction_state(self, address: str) -> object:
        self.calls.append(("query_user_abstraction_state", address))
        return "disabled"

    def spot_user_state(self, address: str) -> object:
        self.calls.append(("spot_user_state", address))
        return {"balances": []}

    def frontend_open_orders(self, address: str, dex: str = "") -> object:
        self.calls.append(("frontend_open_orders", (address, dex)))
        return list(self.open_orders)

    def user_fills(self, address: str) -> object:
        self.calls.append(("user_fills", address))
        return [
            {
                "coin": "SOL",
                "oid": 101,
                "px": "73.10",
                "sz": "0.30",
                "side": "B",
                "time": 1_785_495_600_123,
                "fee": "0.00987",
                "feeToken": "USDC",
                "closedPnl": "0.0",
                "crossed": True,
                "dir": "Open Long",
                "hash": "0xfill",
                "tid": 118_906_512_037_719,
            }
        ]

    def query_order_by_oid(self, user: str, oid: int) -> object:
        self.calls.append(("query_order_by_oid", (user, oid)))
        return {
            "status": "order",
            "order": {
                "order": {"coin": "SOL", "oid": oid, "sz": "0.30"},
                "status": "filled",
                "statusTimestamp": 1_785_495_600_123,
            },
        }

    def user_funding_history(
        self,
        user: str,
        startTime: int,
        endTime: int | None = None,
    ) -> object:
        self.calls.append(("user_funding_history", (user, startTime, endTime)))
        return [
            {
                "time": 1_785_499_200_068,
                "hash": "0xfunding",
                "delta": {
                    "type": "funding",
                    "coin": "SOL",
                    "usdc": "-0.001234",
                    "szi": "0.30",
                    "fundingRate": "0.000056",
                    "nSamples": None,
                },
            }
        ]


class FakeExchange:
    """Record order methods while returning SDK-shaped acknowledgements."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, object]]] = []
        self.entry_response: object = _filled_response(101)
        self.stop_response: object = _resting_response(202)
        self.close_response: object = _filled_response(303)

    def update_leverage(
        self, leverage: int, name: str, is_cross: bool = True
    ) -> object:
        self.calls.append(
            (
                "update_leverage",
                {"leverage": leverage, "name": name, "is_cross": is_cross},
            )
        )
        return {"status": "ok", "response": {"type": "default"}}

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
                    "sz": sz,
                    "px": px,
                    "slippage": slippage,
                    "cloid": cloid,
                    "builder": builder,
                },
            )
        )
        return self.entry_response

    def order(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        order_type: Mapping[str, object],
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
                    "sz": sz,
                    "limit_px": limit_px,
                    "order_type": order_type,
                    "reduce_only": reduce_only,
                    "cloid": cloid,
                    "builder": builder,
                },
            )
        )
        return self.stop_response

    def cancel(self, name: str, oid: int) -> object:
        self.calls.append(("cancel", {"name": name, "oid": oid}))
        return {
            "status": "ok",
            "response": {"type": "cancel", "data": {"statuses": ["success"]}},
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
                    "coin": coin,
                    "sz": sz,
                    "px": px,
                    "slippage": slippage,
                    "cloid": cloid,
                    "builder": builder,
                },
            )
        )
        return self.close_response


def _filled_response(oid: int) -> dict[str, object]:
    return {
        "status": "ok",
        "response": {
            "type": "order",
            "data": {
                "statuses": [
                    {
                        "filled": {
                            "oid": oid,
                            "totalSz": "0.30",
                            "avgPx": "73.10",
                        }
                    }
                ]
            },
        },
    }


def _resting_response(oid: int) -> dict[str, object]:
    return {
        "status": "ok",
        "response": {
            "type": "order",
            "data": {"statuses": [{"resting": {"oid": oid}}]},
        },
    }


def _adapter() -> tuple[SolHyperliquidAdapter, FakeInfo, FakeExchange]:
    info = FakeInfo()
    exchange = FakeExchange()
    adapter = SolHyperliquidAdapter(
        info=info,
        exchange=exchange,
        account_address="0x1111111111111111111111111111111111111111",
        max_notional_usd=22.50,
        slippage_fraction=0.01,
    )
    return adapter, info, exchange


def test_preflight_parses_metadata_fees_account_and_position() -> None:
    """Read-only preflight exposes venue facts without secrets."""
    adapter, _, exchange = _adapter()

    result = adapter.preflight(expected_max_leverage=20)

    assert result.market.symbol == "SOL"
    assert result.market.size_decimals == 2
    assert result.market.max_leverage == 20
    assert result.mark_price == pytest.approx(73.673)
    assert result.price_tick == pytest.approx(0.001)
    assert result.size_step == pytest.approx(0.01)
    assert result.fees.maker_rate == pytest.approx(0.00015)
    assert result.fees.taker_rate == pytest.approx(0.00045)
    assert result.account_value_usd == pytest.approx(150.0)
    assert result.withdrawable_usd == pytest.approx(145.614)
    assert result.position.size_signed == pytest.approx(0.30)
    assert result.position.liquidation_price == pytest.approx(60.50)
    assert result.position.leverage_type == "isolated"
    assert exchange.calls == []


def test_read_only_l2_snapshot_reports_depth_and_pressure() -> None:
    """The TUI book projection is calculated from venue L2, not local inference."""
    adapter, info, exchange = _adapter()

    book = adapter.book_snapshot(depth_levels=5)

    assert book.exchange_timestamp_ms == 1_785_499_200_123
    assert book.mid_price == pytest.approx(73.675)
    assert book.spread_bps == pytest.approx((0.01 / 73.675) * 10_000.0)
    assert book.bid_depth == pytest.approx(15.0)
    assert book.ask_depth == pytest.approx(10.0)
    assert book.order_pressure == pytest.approx(0.2)
    assert [level.price for level in book.bids] == [73.67, 73.66]
    assert [level.size for level in book.asks] == [6.0, 4.0]
    assert ("l2_snapshot", "SOL") in info.calls
    assert exchange.calls == []


def test_configure_leverage_is_explicitly_isolated() -> None:
    """The adapter must never rely on a venue margin-mode default."""
    adapter, _, exchange = _adapter()

    adapter.configure_isolated_leverage(5)

    assert exchange.calls == [
        (
            "update_leverage",
            {"leverage": 5, "name": "SOL", "is_cross": False},
        )
    ]


def test_entry_rounds_down_and_enforces_the_notional_cap() -> None:
    """Lot rounding cannot push a canary entry above its frozen cap."""
    adapter, _, exchange = _adapter()

    ack = adapter.submit_entry(
        side="long",
        requested_notional_usd=22.50,
        mark_price=73.0,
        client_order_id=_CLIENT_ORDER_ID,
    )

    assert ack.accepted is True
    assert ack.oid == 101
    assert ack.status == "filled"
    assert ack.filled_size == pytest.approx(0.30)
    assert ack.average_price == pytest.approx(73.10)
    name, call = exchange.calls[-1]
    assert name == "market_open"
    assert call["name"] == "SOL"
    assert call["is_buy"] is True
    assert call["sz"] == pytest.approx(0.30)
    assert call["px"] == pytest.approx(73.0)
    assert call["slippage"] == pytest.approx(0.01)

    with pytest.raises(HyperliquidAdapterError, match="exceeds.*22.5"):
        adapter.submit_entry(
            side="short",
            requested_notional_usd=22.51,
            mark_price=73.0,
            client_order_id=_CLIENT_ORDER_ID,
        )
    assert len(exchange.calls) == 1


def test_protective_stop_is_opposite_side_reduce_only_market_trigger() -> None:
    """Protection uses the reconciled position size and venue trigger semantics."""
    adapter, _, exchange = _adapter()

    ack = adapter.place_protective_stop(
        position_size_signed=0.30,
        trigger_price=72.40,
        client_order_id=_CLIENT_ORDER_ID,
    )

    assert ack.accepted is True
    assert ack.oid == 202
    name, call = exchange.calls[-1]
    assert name == "order"
    assert call["is_buy"] is False
    assert call["sz"] == pytest.approx(0.30)
    assert call["limit_px"] == pytest.approx(72.40)
    assert call["reduce_only"] is True
    assert call["order_type"] == {
        "trigger": {"triggerPx": 72.40, "isMarket": True, "tpsl": "sl"}
    }


def test_protective_stop_price_is_normalized_to_hyperliquid_wire_precision() -> None:
    """A computed stop with excess precision must not be rejected by the venue."""
    adapter, _, exchange = _adapter()

    adapter.place_protective_stop(
        position_size_signed=0.30,
        trigger_price=73.083616,
        client_order_id=_CLIENT_ORDER_ID,
    )

    _, call = exchange.calls[-1]
    assert call["limit_px"] == pytest.approx(73.084)
    assert call["order_type"] == {
        "trigger": {"triggerPx": 73.084, "isMarket": True, "tpsl": "sl"}
    }


def test_cancel_is_exact_and_close_uses_reduce_only_sdk_operation() -> None:
    """No broad cancellation is available on the narrow adapter surface."""
    adapter, _, exchange = _adapter()

    cancel = adapter.cancel_order(202)
    close = adapter.close_position(
        position_size_signed=0.30,
        mark_price=73.0,
        client_order_id=_CLIENT_ORDER_ID,
    )

    assert cancel.accepted is True
    assert close.accepted is True
    assert close.oid == 303
    assert exchange.calls[0] == ("cancel", {"name": "SOL", "oid": 202})
    assert exchange.calls[1][0] == "market_close"
    assert exchange.calls[1][1]["sz"] == pytest.approx(0.30)
    assert exchange.calls[1][1]["px"] == pytest.approx(73.0)
    assert not hasattr(adapter, "cancel_all")


def test_cancel_transport_loss_preserves_exact_order_identity() -> None:
    """A lost cancel response reports the exact OID for read-side recovery."""
    from hypervector.live.sol_order_transport import SolCancelTransportError

    adapter, _, exchange = _adapter()
    exchange.cancel = Mock(side_effect=RequestException("deadline exceeded"))

    with pytest.raises(SolCancelTransportError) as raised:
        adapter.cancel_order(202)

    assert raised.value.oid == 202
    assert raised.value.operation == "cancel_order"


def test_reconciliation_parses_orders_status_fills_and_flat_state() -> None:
    """Venue state, rather than local intent, determines exposure and fills."""
    adapter, info, _ = _adapter()
    info.open_orders = [
        {
            "coin": "SOL",
            "oid": 202,
            "isTrigger": True,
            "triggerPx": "72.40",
            "origSz": "0.30",
            "sz": "0.30",
            "reduceOnly": True,
            "side": "A",
            "orderType": "Stop Market",
            "timestamp": 1_785_495_600_456,
        }
    ]

    snapshot = adapter.reconcile()
    status = adapter.order_status(101)

    assert snapshot.is_flat is False
    assert snapshot.position.size_signed == pytest.approx(0.30)
    assert snapshot.open_orders[0].oid == 202
    assert snapshot.open_orders[0].reduce_only is True
    assert snapshot.fills[0].oid == 101
    assert snapshot.fills[0].fee_usd == pytest.approx(0.00987)
    assert snapshot.fills[0].trade_id == 118_906_512_037_719
    assert status.status == "filled"
    assert status.oid == 101

    info.position_size = "0"
    info.open_orders = []
    assert adapter.verify_flat() is True


def test_malformed_or_wrong_market_metadata_fails_closed() -> None:
    """Unexpected venue schema or leverage must stop preflight."""
    adapter, info, _ = _adapter()
    original_meta = info.meta
    info.meta = lambda dex="": {  # type: ignore[method-assign]
        "universe": [{"name": "SOL", "szDecimals": 2, "maxLeverage": 10}]
    }

    with pytest.raises(HyperliquidAdapterError, match="max leverage"):
        adapter.preflight(expected_max_leverage=20)

    info.meta = lambda dex="": {"universe": []}  # type: ignore[method-assign]
    with pytest.raises(HyperliquidAdapterError, match="SOL metadata"):
        adapter.preflight(expected_max_leverage=20)
    info.meta = original_meta  # type: ignore[method-assign]


def test_zero_rounded_size_and_non_isolated_position_fail_closed() -> None:
    """Unexecutable size and unexpected cross exposure are technical faults."""
    adapter, info, _ = _adapter()

    with pytest.raises(HyperliquidAdapterError, match="rounds to zero"):
        adapter.submit_entry(
            side="long",
            requested_notional_usd=0.01,
            mark_price=73.0,
            client_order_id=_CLIENT_ORDER_ID,
        )

    state = info.user_state

    def cross_state(address: str, dex: str = "") -> object:
        payload = state(address, dex)
        assert isinstance(payload, dict)
        positions = payload["assetPositions"]
        assert isinstance(positions, list)
        position = positions[0]
        assert isinstance(position, dict)
        details = position["position"]
        assert isinstance(details, dict)
        leverage = details["leverage"]
        assert isinstance(leverage, dict)
        leverage["type"] = "cross"
        return payload

    info.user_state = cross_state  # type: ignore[method-assign]
    with pytest.raises(HyperliquidAdapterError, match="isolated"):
        adapter.reconcile()


def test_funding_history_parses_exact_signed_account_payment() -> None:
    """Funding telemetry uses the venue's account ledger, not an estimate."""
    adapter, info, _ = _adapter()

    payments = adapter.funding_payments(
        start_time_ms=1_785_495_600_000,
        end_time_ms=1_785_499_300_000,
    )

    assert len(payments) == 1
    payment = payments[0]
    assert payment.timestamp_ms == 1_785_499_200_068
    assert payment.usdc_delta == pytest.approx(-0.001234)
    assert payment.position_size_signed == pytest.approx(0.30)
    assert payment.funding_rate == pytest.approx(0.000056)
    assert payment.transaction_hash == "0xfunding"
    assert info.calls[-1][0] == "user_funding_history"
