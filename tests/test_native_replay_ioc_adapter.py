"""Actual native adapter/SDK price arithmetic into the scheduled offline venue."""

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import create_autospec

from hyperliquid.exchange import Exchange
from hyperliquid.utils.types import Cloid
import pytest

from hypervector.live.hyperliquid_perp_adapter import HyperliquidPerpAdapter
from hypervector.live.hyperliquid_protocol import HyperliquidExchangeProtocol, HyperliquidInfoProtocol
from hypervector.live.multi_asset_directional_adapter import MultiAssetDirectionalAdapter
from hypervector.live.asset_order_transport import AssetOrderTransportError
from hypervector.research.native_replay_depth import ExactLevel
from hypervector.research.native_replay_venue import IocOrder, ReceiptTiming
from test_native_replay_adapter import ADDRESS, CLIENT_ID, deny_external_ports
from test_native_replay_depth import book
from test_native_replay_venue import venue

__all__ = ["deny_external_ports"]
D = Decimal


class NativeIocPort:
    """Bind an actual adapter to book/timing inputs without instantiating Exchange."""

    def __init__(self, *, lost: bool, cap: float) -> None:
        """Construct mock protocol boundaries with an explicit synthetic CCC book."""
        self.replay = venue()
        self.lost = lost
        self.requests: list[IocOrder] = []
        info = create_autospec(HyperliquidInfoProtocol, instance=True, spec_set=True)
        info.meta.return_value = {"universe": [{"name": "xyz:CCC", "szDecimals": 3, "maxLeverage": 10}]}
        exchange = create_autospec(HyperliquidExchangeProtocol, instance=True, spec_set=True)
        exchange.market_open.side_effect = self.market_open
        exchange.market_close.side_effect = self.market_close
        self.adapter = MultiAssetDirectionalAdapter(
            HyperliquidPerpAdapter(
                info=info,
                exchange=exchange,
                account_address=ADDRESS,
                max_notional_usd=500,
                slippage_fraction=0.01,
                entry_slippage_fraction=cap,
                symbol="xyz:CCC",
                perp_dex="xyz",
            )
        )

    def market_open(
        self, name: str, is_buy: bool, sz: float, *, px: float, slippage: float, cloid: Cloid
    ) -> object:
        """Use the installed SDK's pure limit calculation with attribute-only input."""
        return self.execute(name, is_buy, sz, px, slippage, cloid, False)

    def market_close(self, name: str, *, sz: float, px: float, slippage: float, cloid: Cloid) -> object:
        """Read true modeled exposure and preserve native reduce-only request size."""
        is_buy = self.replay.account.snapshot().positions[name].quantity_signed < 0
        return self.execute(name, is_buy, sz, px, slippage, cloid, True)

    def execute(
        self, name: str, is_buy: bool, sz: float, px: float, slippage: float, cloid: Cloid, reduce: bool
    ) -> object:
        """Schedule finite execution and return or lose its delayed acknowledgement."""
        dex_asset = 110000
        price_context = SimpleNamespace(
            info=SimpleNamespace(
                name_to_coin={name: name},
                coin_to_asset={name: dex_asset},
                asset_to_sz_decimals={dex_asset: 3},
            )
        )
        limit = Exchange._slippage_price(price_context, name, is_buy, slippage, px)
        now = self.replay.clock.now_ms
        request = IocOrder(
            cloid.to_raw(),
            name,
            "buy" if is_buy else "sell",
            D(str(sz)),
            D(str(limit)),
            D(10),
            D("0.0009"),
            now - 100,
            now,
            now + 50,
            reduce,
        )
        source = replace(book(), source_id=f"fixture:{now}", exchange_time_ms=now + 100)
        if reduce:
            source = replace(
                source, bids=(ExactLevel(D("99.9"), D("0.1")),), asks=(ExactLevel(D("100.1"), D("0.1")),)
            )
        receipts = ReceiptTiming(now + 300, now + 400, now + 200, self.lost)
        self.requests.append(request)
        self.replay.submit(request, source, receipts, maximum_book_delay_ms=50)
        self.replay.advance_to(receipts.response_ms)
        return self.replay.response(request.client_order_id)


@pytest.mark.parametrize("side", ["long", "short"])
@pytest.mark.parametrize("mode", ["partial", "no_fill", "lost"])
def test_actual_ioc_adapter_preserves_cap_quantity_and_transport_identity(side: str, mode: str) -> None:
    """A $500 reference order submits 5 lots; finite depth fills at most 0.3."""
    port = NativeIocPort(lost=mode == "lost", cap=0 if mode == "no_fill" else 0.002)
    kwargs = dict(side=side, requested_notional_usd=500, mark_price=100, client_order_id=CLIENT_ID)
    if mode == "lost":
        with pytest.raises(AssetOrderTransportError) as failure:
            port.adapter.submit_entry(**kwargs)
        assert failure.value.client_order_id == CLIENT_ID and failure.value.ambiguous
    else:
        ack = port.adapter.submit_entry(**kwargs)
        assert ack.client_order_id == CLIENT_ID
        assert ack.filled_size == (None if mode == "no_fill" else 0.3)
    request = port.requests[0]
    assert request.quantity == 5 and request.client_order_id == CLIENT_ID
    assert (
        request.limit_price == D(100)
        if mode == "no_fill"
        else request.limit_price == (D("100.2") if side == "long" else D("99.8"))
    )
    positions = port.replay.account.snapshot().positions
    assert positions == {} if mode == "no_fill" else abs(positions["xyz:CCC"].quantity_signed) == D("0.3")
    assert port.replay.visible_fills() == ()
    port.replay.advance_to(1400)
    assert len(port.replay.visible_fills()) == (0 if mode == "no_fill" else 2)


@pytest.mark.parametrize("side", ["long", "short"])
def test_actual_close_adapter_retains_partial_exposure(side: str) -> None:
    """A finite close receipt reduces only its actual quantity, leaving the remainder."""
    port = NativeIocPort(lost=False, cap=0.002)
    port.adapter.submit_entry(
        side=side, requested_notional_usd=500, mark_price=100, client_order_id=CLIENT_ID
    )
    position = port.replay.account.snapshot().positions["xyz:CCC"]
    ack = port.adapter.close_position(
        position_size_signed=float(position.quantity_signed),
        mark_price=100,
        client_order_id="0x1123456789abcdef0123456789abcdef",
    )
    assert ack.filled_size == 0.1 and port.requests[-1].quantity == D("0.3")
    assert port.requests[-1].reduce_only
    remaining = port.replay.account.snapshot().positions["xyz:CCC"]
    assert abs(remaining.quantity_signed) == D("0.2") and remaining.decision_time_ms == 900
