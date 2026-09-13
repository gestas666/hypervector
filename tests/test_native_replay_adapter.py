"""Native lot sizing into exact-fill economics with offline SDK boundaries."""

from decimal import Decimal
import socket
from unittest.mock import create_autospec

import pytest
import requests

from hypervector.live.hyperliquid_btc_adapter import BtcHyperliquidAdapter
from hypervector.live.hyperliquid_protocol import (
    HyperliquidExchangeProtocol,
    HyperliquidInfoProtocol,
)
from hypervector.live.multi_asset_directional_adapter import MultiAssetDirectionalAdapter
from hypervector.research.native_replay_account import ExactFillAccount
from hypervector.research.native_replay_clock import ReplayClock
from hypervector.research.native_replay_events import FillEvent

ADDRESS = "0x1111111111111111111111111111111111111111"
CLIENT_ID = "0x0123456789abcdef0123456789abcdef"
DECISION_MS = 1_000_000


def denied(*args: object, **kwargs: object) -> object:
    """Make accidental network or real execution-client construction explicit."""
    raise AssertionError("offline native replay attempted a forbidden boundary")


@pytest.fixture(autouse=True)
def deny_external_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use only synthetic SDK ports; do not instantiate a signer or Exchange."""
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(requests.Session, "request", denied)
    monkeypatch.setattr("hyperliquid.exchange.Exchange.__init__", denied)
    monkeypatch.setattr("eth_account.Account.from_key", denied)


class ReceiptPort:
    """Consume only the native adapter's submitted quantity at an explicit price."""

    def __init__(self, price: Decimal) -> None:
        """Initialize explicit cash, source mark and a deterministic receipt clock."""
        self.price = price
        self.clock = ReplayClock(DECISION_MS)
        self.account = ExactFillAccount(Decimal("5000"), ("xyz:SNDK",))
        self.account.mark(
            self.clock.next_stamp(), source_time_ms=DECISION_MS, prices={"xyz:SNDK": Decimal("1630")}
        )
        self.clock.advance_to(DECISION_MS + 1_000)

    def market_open(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        px: float | None = None,
        slippage: float = 0.05,
        cloid: object = None,
    ) -> object:
        """Return a synthetic fill receipt after economic mutation, without resizing."""
        assert name == "xyz:SNDK" and px == 1630.0 and slippage == 0.01
        quantity = Decimal(str(sz))
        dispatch = self.clock.now_ms
        filled = dispatch + 20_000
        self.clock.advance_to(filled + 2_977)
        self.account.mark(self.clock.next_stamp(), source_time_ms=filled, prices={name: self.price})
        self.account.apply_fill(
            FillEvent(
                "fill",
                CLIENT_ID,
                name,
                "buy" if is_buy else "sell",
                quantity,
                self.price,
                quantity * self.price * Decimal("0.0009"),
                Decimal("10"),
                DECISION_MS,
                dispatch,
                filled,
                self.clock.next_stamp(),
                False,
            )
        )
        return {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {
                    "statuses": [{"filled": {"oid": 101, "totalSz": str(sz), "avgPx": str(self.price)}}],
                },
            },
        }


@pytest.mark.parametrize("side", ["long", "short"])
@pytest.mark.parametrize("price", [Decimal("1620"), Decimal("1640")])
def test_native_reference_sizing_survives_a_delayed_fill(side: str, price: Decimal) -> None:
    """The actual adapter floors at reference; the delayed fill changes cash cost."""
    info = create_autospec(HyperliquidInfoProtocol, instance=True, spec_set=True)
    info.meta.return_value = {
        "universe": [
            {"name": "xyz:SNDK", "szDecimals": 3, "maxLeverage": 20},
        ]
    }
    exchange = create_autospec(HyperliquidExchangeProtocol, instance=True, spec_set=True)
    port = ReceiptPort(price)
    exchange.market_open.side_effect = port.market_open
    adapter = MultiAssetDirectionalAdapter(
        BtcHyperliquidAdapter(
            info=info,
            exchange=exchange,
            account_address=ADDRESS,
            max_notional_usd=500,
            slippage_fraction=0.01,
            symbol="xyz:SNDK",
            perp_dex="xyz",
        )
    )
    ack = adapter.submit_entry(
        side=side, requested_notional_usd=500, mark_price=1630, client_order_id=CLIENT_ID
    )
    view = port.account.snapshot()
    position = view.positions["xyz:SNDK"]
    assert ack.filled_size == 0.306 and ack.average_price == float(price)
    assert abs(position.quantity_signed) == Decimal("0.306")
    assert position.quantity_signed > 0 if side == "long" else position.quantity_signed < 0
    assert position.entry_notional_usd == Decimal("0.306") * price
    assert position.decision_time_ms == DECISION_MS
    assert position.first_fill_time_ms == DECISION_MS + 21_000
    assert view.stamp.observed_time_ms == DECISION_MS + 23_977
    assert view.cash_usd == Decimal("5000") - Decimal("0.306") * price * Decimal("0.0009")
    assert view.equity_usd == view.cash_usd
    assert position.entry_notional_usd > 500 if price == 1640 else position.entry_notional_usd < 500
