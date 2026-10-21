"""Fail-closed construction tests for the bidirectional cohort authority."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from hypervector.live.bidirectional_cohort_factory import (
    AssetExecutionEnvelope,
    create_armed_multi_asset_adapters,
)
from hypervector.live.hyperliquid_protocol import (
    HyperliquidExchangeProtocol,
    HyperliquidInfoProtocol,
    HyperliquidLiveAdapterProtocol,
)
from hypervector.live.hyperliquid_sdk_factory import HyperliquidSdkBuilderProtocol
from hypervector.live.policy import SECRET_ENV_API_KEY, SECRET_ENV_WALLET

_ADDRESS = "0x1111111111111111111111111111111111111111"


class _Builder(HyperliquidSdkBuilderProtocol):
    """Record authenticated construction without network access."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[str, ...]]] = []
        self.info = Mock(spec=HyperliquidInfoProtocol)
        self.exchange = Mock(spec=HyperliquidExchangeProtocol)

    def build(
        self,
        *,
        account_address: str,
        private_key: str,
        perp_dexes: tuple[str, ...] = (),
    ) -> tuple[HyperliquidInfoProtocol, HyperliquidExchangeProtocol]:
        """Return one inert SDK pair."""
        self.calls.append((account_address, private_key, perp_dexes))
        return self.info, self.exchange


def test_one_sdk_build_constructs_every_configured_symbol() -> None:
    """The authority is multi-asset rather than a BTC/SOL special case."""
    builder = _Builder()
    assets = tuple(
        AssetExecutionEnvelope(
            symbol=symbol,
            max_notional_usd=25.0,
            slippage_fraction=0.01,
        )
        for symbol in ("BTC", "ETH", "SOL", "HYPE")
    )

    adapters = create_armed_multi_asset_adapters(
        assets,
        enabled=True,
        accepts_live_risk=True,
        environ={SECRET_ENV_WALLET: _ADDRESS, SECRET_ENV_API_KEY: "private"},
        builder=builder,
    )

    assert adapters.symbols == ("BTC", "ETH", "SOL", "HYPE")
    assert tuple(adapters.by_symbol) == adapters.symbols
    assert all(
        adapters.by_symbol[symbol].symbol == symbol for symbol in adapters.symbols
    )
    assert all(
        isinstance(adapters.by_symbol[symbol], HyperliquidLiveAdapterProtocol)
        for symbol in adapters.symbols
    )
    assert builder.calls == [(_ADDRESS, "private", ())]


def test_one_sdk_build_receives_exact_hip3_namespace_roster() -> None:
    """The authenticated SDK loads each required builder-perp namespace once."""
    builder = _Builder()
    assets = (
        AssetExecutionEnvelope("BTC", 25.0, 0.01),
        AssetExecutionEnvelope("xyz:AAA", 25.0, 0.01),
        AssetExecutionEnvelope("xyz:DDD", 25.0, 0.01),
    )

    adapters = create_armed_multi_asset_adapters(
        assets,
        enabled=True,
        accepts_live_risk=True,
        environ={SECRET_ENV_WALLET: _ADDRESS, SECRET_ENV_API_KEY: "private"},
        builder=builder,
    )

    assert builder.calls == [(_ADDRESS, "private", ("", "xyz"))]
    assert adapters.by_symbol["BTC"].perp_dex == ""
    assert adapters.by_symbol["xyz:AAA"].perp_dex == "xyz"
    assert adapters.by_symbol["xyz:DDD"].perp_dex == "xyz"


def test_execution_envelope_preserves_exact_hip3_namespace() -> None:
    """An exact HIP-3 venue identity carries its perp-dex into the SDK layer."""
    asset = AssetExecutionEnvelope("xyz:AAA", 25.0, 0.01)

    assert asset.symbol == "xyz:AAA"
    assert asset.perp_dex == "xyz"


@pytest.mark.parametrize("symbol", ["XYZ:AAA", "xyz:aaa", "xyz:", "BTC:USD"])
def test_execution_envelope_rejects_malformed_namespaces(symbol: str) -> None:
    """Malformed or ambiguous namespaced symbols fail before SDK construction."""
    with pytest.raises(ValueError, match="venue identity"):
        AssetExecutionEnvelope(symbol, 25.0, 0.01)


@pytest.mark.parametrize(
    ("enabled", "accepts_live_risk", "message"),
    [(False, True, "--enabled"), (True, False, "--i-accept-live-risk")],
)
def test_multi_asset_factory_refuses_before_sdk_build(
    enabled: bool,
    accepts_live_risk: bool,
    message: str,
) -> None:
    """Neither credentials nor multiple assets bypass explicit arming."""
    builder = _Builder()
    asset = AssetExecutionEnvelope("BTC", 25.0, 0.01)

    with pytest.raises(ValueError, match=message):
        create_armed_multi_asset_adapters(
            (asset,),
            enabled=enabled,
            accepts_live_risk=accepts_live_risk,
            environ={SECRET_ENV_WALLET: _ADDRESS, SECRET_ENV_API_KEY: "private"},
            builder=builder,
        )

    assert builder.calls == []


@pytest.mark.parametrize("requested", [0, -1, 2.5, True])
def test_envelope_refuses_malformed_requested_leverage(requested: object) -> None:
    """A malformed requested leverage fails before any SDK construction."""
    with pytest.raises(ValueError, match="requested leverage must be a positive"):
        AssetExecutionEnvelope("SOL", 25.0, 0.01, requested_leverage=requested)


def test_armed_adapters_carry_each_market_requested_leverage() -> None:
    """The live factory forwards each market's requested leverage to preflight."""
    builder = _Builder()
    assets = (
        AssetExecutionEnvelope("BTC", 25.0, 0.01, requested_leverage=10),
        AssetExecutionEnvelope("SOL", 25.0, 0.01),
    )

    adapters = create_armed_multi_asset_adapters(
        assets,
        enabled=True,
        accepts_live_risk=True,
        environ={SECRET_ENV_WALLET: _ADDRESS, SECRET_ENV_API_KEY: "private"},
        builder=builder,
    )

    assert adapters.by_symbol["BTC"]._requested_leverage == 10
    assert adapters.by_symbol["SOL"]._requested_leverage is None
