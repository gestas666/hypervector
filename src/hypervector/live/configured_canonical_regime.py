"""Select independently classified context for explicitly supported cohort routes."""

from hypervector.live.canonical_regime_telemetry import canonical_regime_symbols
from hypervector.live.hourly_price_provider import HOURLY_PRICE_STRATEGIES
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig


def configured_canonical_regime_symbols(
    config: MultiAssetLiveConfig,
) -> tuple[str, ...]:
    """Add hourly routes whose detector resets at each one-minute source gap.

    This is descriptive telemetry; neither intents nor regime entry gates are added.
    Older session-based mechanisms keep their existing provider-only scope.
    """
    supported = set(canonical_regime_symbols(config.symbols))
    supported.update(
        symbol
        for provider in config.providers
        if provider.strategy_id in HOURLY_PRICE_STRATEGIES
        for symbol in provider.symbols
    )
    return tuple(symbol for symbol in config.symbols if symbol in supported)
