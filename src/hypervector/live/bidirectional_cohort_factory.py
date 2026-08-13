"""Fail-closed single-authority construction for the Hulk and SOL cohort."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import os
from types import MappingProxyType

from hypervector.live.hulk_smash_live_config import HulkSmashLiveConfig
from hypervector.live.hyperliquid_btc_adapter import BtcHyperliquidAdapter
from hypervector.live.hyperliquid_sol_adapter import SolHyperliquidAdapter
from hypervector.live.hyperliquid_sol_factory import (
    OfficialSolSdkBuilder,
    SolSdkBuilderProtocol,
)
from hypervector.live.hyperliquid_sol_parsing import validate_address
from hypervector.live.multi_asset_directional_adapter import (
    MultiAssetDirectionalAdapter,
)
from hypervector.live.perp_venue_identity import (
    configured_perp_dexes,
    parse_perp_venue_identity,
)
from hypervector.live.policy import SECRET_ENV_API_KEY, SECRET_ENV_WALLET
from hypervector.live.serialized_hyperliquid_clients import shared_serialized_clients
from hypervector.live.sol_range_onset_config import SolRangeOnsetConfig


@dataclass(frozen=True)
class BidirectionalCohortAdapters:
    """The two symbol adapters sharing one serialized SDK authority."""

    btc: BtcHyperliquidAdapter
    sol: SolHyperliquidAdapter


@dataclass(frozen=True)
class AssetExecutionEnvelope:
    """One enabled symbol's venue-side notional and slippage bounds."""

    symbol: str
    max_notional_usd: float
    slippage_fraction: float
    perp_dex: str = field(init=False)

    def __post_init__(self) -> None:
        """Reject malformed asset authority before SDK construction."""
        identity = parse_perp_venue_identity(self.symbol)
        if self.max_notional_usd <= 0.0:
            raise ValueError("asset max_notional_usd must be positive")
        if not 0.0 <= self.slippage_fraction <= 0.05:
            raise ValueError("asset slippage_fraction must be between zero and 0.05")
        object.__setattr__(self, "symbol", identity.symbol)
        object.__setattr__(self, "perp_dex", identity.perp_dex)


@dataclass(frozen=True)
class MultiAssetCohortAdapters:
    """All configured symbol adapters sharing one SDK authority."""

    symbols: tuple[str, ...]
    by_symbol: Mapping[str, MultiAssetDirectionalAdapter]


def create_armed_bidirectional_adapters(
    hulk: HulkSmashLiveConfig,
    sol: SolRangeOnsetConfig,
    *,
    environ: Mapping[str, str] | None = None,
    builder: SolSdkBuilderProtocol | None = None,
) -> BidirectionalCohortAdapters:
    """Construct both live adapters from exactly one authenticated SDK build."""
    env = environ if environ is not None else os.environ
    address = (env.get(SECRET_ENV_WALLET) or "").strip()
    private_key = (env.get(SECRET_ENV_API_KEY) or "").strip()
    credentials_present = bool(address and private_key)
    hulk.require_live_start(credentials_present=credentials_present)
    sol.require_live_start(credentials_present=credentials_present)
    validated_address = validate_address(address)
    sdk_builder = builder if builder is not None else OfficialSolSdkBuilder()
    raw_info, raw_exchange = sdk_builder.build(
        account_address=validated_address,
        private_key=private_key,
    )
    info, exchange = shared_serialized_clients(raw_info, raw_exchange)
    return BidirectionalCohortAdapters(
        btc=BtcHyperliquidAdapter(
            info=info,
            exchange=exchange,
            account_address=validated_address,
            max_notional_usd=hulk.max_notional_usd,
            slippage_fraction=hulk.market_slippage_cap_fraction,
        ),
        sol=SolHyperliquidAdapter(
            info=info,
            exchange=exchange,
            account_address=validated_address,
            max_notional_usd=sol.max_notional_usd,
            slippage_fraction=sol.market_slippage_cap_fraction,
        ),
    )


def create_armed_multi_asset_adapters(
    assets: tuple[AssetExecutionEnvelope, ...],
    *,
    enabled: bool,
    accepts_live_risk: bool,
    environ: Mapping[str, str] | None = None,
    builder: SolSdkBuilderProtocol | None = None,
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
    sdk_builder = builder if builder is not None else OfficialSolSdkBuilder()
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
            BtcHyperliquidAdapter(
                info=info,
                exchange=exchange,
                account_address=validated_address,
                max_notional_usd=asset.max_notional_usd,
                slippage_fraction=asset.slippage_fraction,
                symbol=asset.symbol,
                perp_dex=asset.perp_dex,
            )
        )
        for asset in assets
    }
    return MultiAssetCohortAdapters(
        symbols=symbols,
        by_symbol=MappingProxyType(adapters),
    )
