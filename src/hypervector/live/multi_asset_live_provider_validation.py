"""Provider-scope validation for the shared multi-asset live configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError
from hypervector.live.provider_registry import validate_registered_provider

if TYPE_CHECKING:
    from hypervector.live.multi_asset_live_config import (
        AssetLiveConfig,
        MultiAssetLiveConfig,
        StrategyProviderConfig,
    )


def validate_provider_scope(
    config: MultiAssetLiveConfig,
    enabled: set[str],
) -> None:
    """Require exact declared scope, safe sizing, and a provider for every asset."""
    supported = {symbol: set() for symbol in config.symbols}
    assets = {asset.symbol: asset for asset in config.assets}
    for provider in config.providers:
        _validate_provider_symbols(provider, enabled)
        _validate_entry_capability(provider)
        _validate_provider_overrides(provider)
        _validate_provider_sizing(provider, assets)
        validate_registered_provider(provider)
        for symbol in provider.symbols:
            supported[symbol].update(provider.sides)
    missing = [symbol for symbol, sides in supported.items() if not sides]
    if missing:
        raise MultiAssetLiveConfigError(
            f"enabled symbols require at least one provider: {missing}"
        )
    if config.mode == "live" and not config.executable_provider_symbols:
        raise MultiAssetLiveConfigError(
            "cohort requires at least one explicit provider execution symbol"
        )


def _validate_provider_symbols(
    provider: StrategyProviderConfig,
    enabled: set[str],
) -> None:
    if not set(provider.symbols).issubset(enabled):
        raise MultiAssetLiveConfigError("provider references a disabled symbol")
    if len(set(provider.execution_symbols)) != len(provider.execution_symbols):
        raise MultiAssetLiveConfigError("provider execution_symbols must be unique")
    if not set(provider.execution_symbols).issubset(provider.symbols):
        raise MultiAssetLiveConfigError(
            "provider execution_symbols must be observed by that provider"
        )


def _validate_entry_capability(provider: StrategyProviderConfig) -> None:
    contracts = (
        (provider.execution,)
        + tuple(
            provider.execution_for(symbol) for symbol, _ in provider.stop_bps_overrides
        )
        + tuple(
            provider.execution_for(override.symbol, override.side)
            for override in provider.profit_lock_overrides
        )
    )
    if any(contract.entry_liquidity != "taker_ioc" for contract in contracts):
        raise MultiAssetLiveConfigError(
            "shared cohort market entry adapter requires taker_ioc; "
            "maker_post_only is not implemented"
        )


def _validate_provider_overrides(provider: StrategyProviderConfig) -> None:
    observed = set(provider.symbols)
    override_symbols = {symbol for symbol, _ in provider.execution_side_overrides}
    stop_symbols = {symbol for symbol, _ in provider.stop_bps_overrides}
    sizing_symbols = {symbol for symbol, _ in provider.sizing_overrides}
    directional = {symbol for symbol, _, _ in provider.directional_sizing_overrides}
    lock_symbols = {override.symbol for override in provider.profit_lock_overrides}
    checks = (
        (override_symbols, "execution_side_overrides"),
        (stop_symbols, "stop_bps_overrides"),
        (sizing_symbols, "sizing_overrides"),
        (directional, "directional sizing"),
        (lock_symbols, "profit_lock_overrides"),
    )
    for symbols, label in checks:
        if not symbols.issubset(observed):
            raise MultiAssetLiveConfigError(
                f"provider {label} must reference observed symbols"
            )
    for _symbol, sides in provider.execution_side_overrides:
        if not sides.issubset(provider.sides):
            raise MultiAssetLiveConfigError("execution override exceeds signal sides")
    if provider.stop_bps_overrides and provider.execution.stop_policy != "fixed_bps":
        raise MultiAssetLiveConfigError(
            "provider stop_bps_overrides require a fixed_bps stop policy"
        )
    for override in provider.profit_lock_overrides:
        if override.side not in provider.executable_sides(override.symbol):
            raise MultiAssetLiveConfigError(
                "provider profit_lock_overrides exceed executable direction scope"
            )


def _validate_provider_sizing(
    provider: StrategyProviderConfig,
    assets: dict[str, AssetLiveConfig],
) -> None:
    for symbol, sizing in provider.sizing_overrides:
        asset = assets[symbol]
        if sizing.max_notional_usd > asset.max_notional_usd:
            raise MultiAssetLiveConfigError(
                "provider sizing override exceeds the asset adapter ceiling"
            )
    for symbol, side, sizing in provider.directional_sizing_overrides:
        if side not in provider.executable_sides(symbol):
            raise MultiAssetLiveConfigError(
                "provider directional sizing exceeds executable direction scope"
            )
        asset = assets[symbol]
        if sizing.max_notional_usd > asset.max_notional_usd:
            raise MultiAssetLiveConfigError(
                "provider directional sizing exceeds the asset adapter ceiling"
            )
