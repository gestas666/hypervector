"""Fail-closed single-authority construction of every cohort symbol adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import os
from types import MappingProxyType

from hypervector.live.hyperliquid_perp_adapter import HyperliquidPerpAdapter
from hypervector.live.hyperliquid_perp_reader import require_requested_leverage
from hypervector.live.hyperliquid_sdk_factory import (
    OfficialHyperliquidSdkBuilder,
    HyperliquidSdkBuilderProtocol,
)
from hypervector.live.hyperliquid_parsing import validate_address
from hypervector.live.multi_asset_directional_adapter import (
    MultiAssetDirectionalAdapter,
)
from hypervector.live.perp_venue_identity import (
    configured_perp_dexes,
    parse_perp_venue_identity,
)
from hypervector.live.policy import SECRET_ENV_API_KEY, SECRET_ENV_WALLET
from hypervector.live.serialized_hyperliquid_clients import shared_serialized_clients


@dataclass(frozen=True)
class AssetExecutionEnvelope:
    """One enabled symbol's venue-side notional and slippage bounds."""

    symbol: str
    max_notional_usd: float
    slippage_fraction: float
    entry_slippage_fraction: float | None = None
    requested_leverage: int | None = None
    perp_dex: str = field(init=False)

    def __post_init__(self) -> None:
        """Reject malformed asset authority before SDK construction."""
        identity = parse_perp_venue_identity(self.symbol)
        if self.max_notional_usd <= 0.0:
            raise ValueError("asset max_notional_usd must be positive")
        if not 0.0 <= self.slippage_fraction <= 0.05:
            raise ValueError("asset slippage_fraction must be between zero and 0.05")
        if self.entry_slippage_fraction is not None and not (
            0.0 <= self.entry_slippage_fraction <= 0.05
        ):
            raise ValueError(
                "asset entry_slippage_fraction must be between zero and 0.05"
            )
        if self.requested_leverage is not None:
            require_requested_leverage(identity.symbol, self.requested_leverage)
        object.__setattr__(self, "symbol", identity.symbol)
        object.__setattr__(self, "perp_dex", identity.perp_dex)


@dataclass(frozen=True)
class MultiAssetCohortAdapters:
    """All configured symbol adapters sharing one SDK authority."""

    symbols: tuple[str, ...]
    by_symbol: Mapping[str, MultiAssetDirectionalAdapter]


def create_armed_multi_asset_adapters(
    assets: tuple[AssetExecutionEnvelope, ...],
    *,
    enabled: bool,
    accepts_live_risk: bool,
    environ: Mapping[str, str] | None = None,
    builder: HyperliquidSdkBuilderProtocol | None = None,
    read_coalesce_seconds: float = 0.0,
) -> MultiAssetCohortAdapters:
    """Construct every enabled symbol adapter from one authenticated SDK pair."""
    if not assets:
        raise ValueError("multi-asset cohort requires at least one symbol")
    symbols = tuple(asset.symbol for asset in assets)
    if len(set(symbols)) != len(symbols):
        raise ValueError("multi-asset cohort symbols must be unique")
    if not enabled:
        raise ValueError("live start requires --enabled")
    if not accepts_live_risk:
        raise ValueError("live start requires --i-accept-live-risk")
    env = environ if environ is not None else os.environ
    address = (env.get(SECRET_ENV_WALLET) or "").strip()
    private_key = (env.get(SECRET_ENV_API_KEY) or "").strip()
    if not address or not private_key:
        raise ValueError("live start requires configured Hyperliquid credentials")
    validated_address = validate_address(address)
    sdk_builder = builder if builder is not None else OfficialHyperliquidSdkBuilder()
    perp_dexes = configured_perp_dexes(symbols)
    if perp_dexes:
        raw_info, raw_exchange = sdk_builder.build(
            account_address=validated_address,
            private_key=private_key,
            perp_dexes=perp_dexes,
        )
    else:
        raw_info, raw_exchange = sdk_builder.build(
            account_address=validated_address,
            private_key=private_key,
        )
    info, exchange = shared_serialized_clients(
        raw_info,
        raw_exchange,
        read_coalesce_seconds=read_coalesce_seconds,
    )
    adapters = {
        asset.symbol: MultiAssetDirectionalAdapter(
            HyperliquidPerpAdapter(
                info=info,
                exchange=exchange,
                account_address=validated_address,
                max_notional_usd=asset.max_notional_usd,
                slippage_fraction=asset.slippage_fraction,
                entry_slippage_fraction=asset.entry_slippage_fraction,
                symbol=asset.symbol,
                perp_dex=asset.perp_dex,
            ),
            requested_leverage=asset.requested_leverage,
        )
        for asset in assets
    }
    return MultiAssetCohortAdapters(
        symbols=symbols,
        by_symbol=MappingProxyType(adapters),
    )
