"""Every runner refusal that is knowable from a loaded profile alone.

``MultiAssetLiveRunner.__init__`` refuses several configuration shapes that the
loader, the read-only preflight and the observe runner all accept. Those refusals
used to fire only after the mandatory pre-start backup, the full ledger replay and
the construction of an authenticated, signing-capable venue client — about
thirteen minutes into an armed start, once per retry.

Everything here is pure: no credentials, no venue client, no filesystem writes. The
armed entrypoint runs it before any of that work, and the offline gate calls the
same function, so the two cannot drift.
"""

from __future__ import annotations

from hypervector.live.bidirectional_intents import (
    BidirectionalIntentRouter,
    StrategyCapability,
)
from hypervector.live.cohort_entry_submission import (
    entry_delays_from_providers,
    validate_entry_delays,
)
from hypervector.live.cohort_route_cycle import provider_bounded_fallback_hold_ms
from hypervector.live.multi_asset_execution_authority import (
    effective_execution_directions,
    hold_milliseconds,
)
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.live.multi_asset_live_runner_support import validate_runtime


def build_cohort_router(config: MultiAssetLiveConfig) -> BidirectionalIntentRouter:
    """Construct declared provider capabilities without performance gates."""
    capabilities = tuple(
        StrategyCapability(
            provider.strategy_id,
            symbol,
            provider.sides,
            provider.priority,
            provider.position_policy,
        )
        for symbol in config.symbols
        for provider in config.providers
        if symbol in provider.symbols
    )
    return BidirectionalIntentRouter(
        capabilities,
        maximum_positions=config.maximum_positions,
    )


def validate_runtime_configuration(config: MultiAssetLiveConfig) -> None:
    """Raise exactly what the runner would raise at construction, for free.

    Placeholder engines are sufficient because every construction-time validator
    inspects engines only by key.
    """
    engines = {symbol: object() for symbol in config.symbols}
    contracts = config.provider_execution_contracts
    executable_pairs = config.executable_provider_symbols
    directions = effective_execution_directions(
        executable_pairs, config.executable_provider_directions
    )
    holds = hold_milliseconds(
        {asset.symbol: asset.maximum_hold_seconds for asset in config.assets}
    )
    validate_runtime(
        config.symbols,
        engines,
        build_cohort_router(config),
        config.poll_seconds,
        {asset.symbol: asset.maximum_hold_seconds for asset in config.assets},
        contracts,
        executable_pairs,
        directions,
        config.provider_entry_sizing,
        config.provider_directional_entry_sizing,
    )
    provider_bounded_fallback_hold_ms(holds, contracts, executable_pairs)
    validate_entry_delays(
        entry_delays_from_providers(config.providers), executable_pairs
    )
