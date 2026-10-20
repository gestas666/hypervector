"""Provider-scope validation for the shared multi-asset live configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hypervector.live.btc_hulk_robust_short_provider import HULK_SHORT_STRATEGIES
from hypervector.live.btc_liquidity_sweep_long_provider import (
    LIQUIDITY_SWEEP_LONG_STRATEGIES,
)
from hypervector.live.btc_structural_contract import BTC_STRUCTURAL_FIXED60_STRATEGY
from hypervector.live.directional_range_onset_provider import (
    ETH_RANGE_LONG_STRATEGY,
    SOL_RANGE_SHORT_STRATEGY,
)
from hypervector.live.eth_breakout_transfer_provider import (
    ETH_BREAKOUT_TRANSFER_STRATEGY,
)
from hypervector.live.hype_breakout_compression_provider import (
    HYPE_COMPRESSION_BREAKOUT_STRATEGY,
)
from hypervector.live.hype_breakout_retest_provider import (
    HYPE_BREAKOUT_RETEST_STRATEGY,
)
from hypervector.live.hype_compression_alignment_provider import (
    HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
)
from hypervector.live.hype_native_breakout_provider import (
    HYPE_NATIVE_BREAKOUT_LONG_STRATEGY,
    HYPE_NATIVE_BREAKOUT_STRATEGY,
)
from hypervector.live.hype_relaxed_contract import HYPE_RELAXED_STRATEGIES
from hypervector.live.hip3_cash_open_gap_provider import (
    HIP3_SPCX_CASH_OPEN_STRATEGY,
)
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError
from hypervector.live.multi_asset_route_contract_validation import (
    binds_signal_anchors,
    validate_reused_route_contract,
)
from hypervector.live.multi_asset_special_provider_validation import (
    validate_hype_compression_alignment,
    validate_hype_native_breakout,
    validate_research_pending_market_observer,
    validate_spcx_cash_open,
)
from hypervector.live.sol_aligned_range_contract import (
    SOL_ALIGNED_RANGE_FIXED60_STRATEGY,
)
from hypervector.live.spcx_cash_session_breakout_provider import (
    SPCX_CASH_SESSION_LONG_STRATEGY,
)
from hypervector.live.research_pending_market_observer import (
    RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY,
)
from hypervector.live.zec_donchian_provider import ZEC_DONCHIAN_LONG_STRATEGY
from hypervector.live.hourly_price_provider import HOURLY_PRICE_STRATEGIES
from hypervector.live.hourly_price_contract import validate_hourly_price_provider
from hypervector.live.fixed_route_provider_validation import (
    validate_directional_range,
    validate_spcx_cash_session_long,
    validate_zec_donchian_long,
)

if TYPE_CHECKING:
    from hypervector.live.multi_asset_live_config import (
        AssetLiveConfig,
        MultiAssetLiveConfig,
        StrategyProviderConfig,
    )

_BOTH_SIDES = frozenset({"long", "short"})
_SOURCE_FOLLOW = "hypervelocity_source_follow_bidirectional_5m_v1"
_HYPE_BREAKOUT = "hype_breakout_onset_bidirectional_v1"
_RANGE_ONSET = "range_onset_bidirectional_v1"
_HYPE_STRATEGIES = HYPE_RELAXED_STRATEGIES | {
    _HYPE_BREAKOUT,
    HYPE_COMPRESSION_BREAKOUT_STRATEGY,
    HYPE_BREAKOUT_RETEST_STRATEGY,
}


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
        _validate_provider_source(provider)
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
    context_symbols = {symbol for symbol, _ in provider.entry_context_overrides}
    stop_symbols = {symbol for symbol, _ in provider.stop_bps_overrides}
    sizing_symbols = {symbol for symbol, _ in provider.sizing_overrides}
    directional = {symbol for symbol, _, _ in provider.directional_sizing_overrides}
    lock_symbols = {override.symbol for override in provider.profit_lock_overrides}
    checks = (
        (override_symbols, "execution_side_overrides"),
        (context_symbols, "entry_context_overrides"),
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


def _validate_provider_source(provider: StrategyProviderConfig) -> None:
    strategy = provider.strategy_id
    is_source_follow = strategy == _SOURCE_FOLLOW
    if not is_source_follow and provider.source_profile is not None:
        raise MultiAssetLiveConfigError(
            "source_profile is only valid for the measured source-follow provider"
        )
    if provider.entry_context_overrides and strategy != _RANGE_ONSET:
        raise MultiAssetLiveConfigError(
            "entry_context_overrides are only valid for range onset"
        )
    _validate_known_provider(provider)
    if not is_source_follow:
        return
    if provider.symbols != ("BTC",) or provider.timeframe != "5m":
        raise MultiAssetLiveConfigError(
            "measured source-follow provider requires BTC on the 5m timeframe"
        )
    if provider.source_profile is None:
        raise MultiAssetLiveConfigError(
            "measured source-follow provider requires source_profile"
        )


def _validate_known_provider(provider: StrategyProviderConfig) -> None:
    strategy = provider.strategy_id
    validate_reused_route_contract(provider)
    if strategy == _HYPE_BREAKOUT:
        _validate_cross_asset_breakout(provider)
    elif strategy in {
        HYPE_NATIVE_BREAKOUT_STRATEGY,
        HYPE_NATIVE_BREAKOUT_LONG_STRATEGY,
    }:
        validate_hype_native_breakout(provider)
    elif strategy == HYPE_COMPRESSION_BREAKOUT_STRATEGY:
        _validate_hype_compression(provider)
    elif strategy == HYPE_COMPRESSION_ALIGNMENT_STRATEGY:
        validate_hype_compression_alignment(provider)
    elif strategy in _HYPE_STRATEGIES:
        _validate_hype_breakout(provider)
    if strategy == ETH_BREAKOUT_TRANSFER_STRATEGY:
        _validate_eth_transfer(provider)
    if strategy == _RANGE_ONSET:
        _validate_range_onset(provider)
    if strategy == BTC_STRUCTURAL_FIXED60_STRATEGY:
        _validate_btc_structural(provider)
    if strategy == SOL_ALIGNED_RANGE_FIXED60_STRATEGY:
        _validate_sol_aligned_range(provider)
    if strategy in HULK_SHORT_STRATEGIES:
        _validate_hulk_robust_short(provider)
    if strategy in LIQUIDITY_SWEEP_LONG_STRATEGIES:
        _validate_liquidity_sweep_long(provider)
    if strategy == HIP3_SPCX_CASH_OPEN_STRATEGY:
        validate_spcx_cash_open(provider)
    if strategy == RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY:
        validate_research_pending_market_observer(provider)
    if strategy in {ETH_RANGE_LONG_STRATEGY, SOL_RANGE_SHORT_STRATEGY}:
        validate_directional_range(provider)
    if strategy == ZEC_DONCHIAN_LONG_STRATEGY:
        validate_zec_donchian_long(provider)
    if strategy in HOURLY_PRICE_STRATEGIES:
        validate_hourly_price_provider(provider)
    if strategy == SPCX_CASH_SESSION_LONG_STRATEGY:
        validate_spcx_cash_session_long(provider)


def _validate_hype_breakout(provider: StrategyProviderConfig) -> None:
    if "HYPE" not in provider.symbols or provider.timeframe != "1m":
        raise MultiAssetLiveConfigError(
            "HT-Breakout provider requires HYPE observation and the 1m source timeframe"
        )


def _validate_cross_asset_breakout(provider: StrategyProviderConfig) -> None:
    supported = {"BTC", "ETH", "SOL", "HYPE"}
    if (
        not provider.symbols
        or not set(provider.symbols).issubset(supported)
        or provider.timeframe != "1m"
    ):
        raise MultiAssetLiveConfigError(
            "cross-asset HT-Breakout requires supported symbols and the 1m source timeframe"
        )


def _validate_hype_compression(provider: StrategyProviderConfig) -> None:
    valid = (
        provider.symbols == ("HYPE",)
        and provider.sides == _BOTH_SIDES
        and provider.timeframe == "1m"
        and binds_signal_anchors(provider.execution, stop_anchor=False)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "HYPE compression breakout requires HYPE-only 1m scope, both emitted "
            "sides, a fixed stop, and no absolute target"
        )


def _validate_eth_transfer(provider: StrategyProviderConfig) -> None:
    valid = (
        provider.symbols == ("ETH",)
        and provider.sides == _BOTH_SIDES
        and provider.timeframe == "1m"
        and provider.position_policy == "enter_and_close"
        and binds_signal_anchors(provider.execution, stop_anchor=False)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "ETH breakout transfer requires ETH-only 1m scope, both emitted sides, "
            "opposite-entry close, a fixed stop, and no absolute target"
        )


def _validate_range_onset(provider: StrategyProviderConfig) -> None:
    """Require the core symbols and both sides the hourly-cross signal emits."""
    valid = (
        bool(provider.symbols)
        and set(provider.symbols).issubset({"BTC", "ETH", "SOL", "HYPE"})
        and provider.sides == _BOTH_SIDES
        and provider.timeframe == "1m"
        and binds_signal_anchors(provider.execution, stop_anchor=False)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "range onset requires supported core symbols, both emitted sides, 1m "
            "source polling, a fixed stop, and no absolute target"
        )


def _validate_btc_structural(provider: StrategyProviderConfig) -> None:
    if (
        provider.symbols != ("BTC",)
        or provider.timeframe != "1m"
        or provider.execution_symbols not in {(), ("BTC",)}
        or provider.source_profile is not None
    ):
        raise MultiAssetLiveConfigError(
            "BTC structural provider requires the 1m source timeframe, BTC-only "
            "observation, and at most BTC-only execution authority"
        )


def _validate_sol_aligned_range(provider: StrategyProviderConfig) -> None:
    if (
        provider.symbols != ("SOL",)
        or provider.timeframe != "1m"
        or provider.execution_symbols not in {(), ("SOL",)}
        or provider.source_profile is not None
        or provider.position_policy != "flat_entry_only"
    ):
        raise MultiAssetLiveConfigError(
            "SOL aligned-range provider requires the 1m source timeframe, SOL-only "
            "observation, at most SOL-only execution authority, and flat-entry-only "
            "position handling"
        )


def _validate_hulk_robust_short(provider: StrategyProviderConfig) -> None:
    valid = (
        provider.symbols == ("BTC",)
        and "short" in provider.sides
        and provider.timeframe == "30m"
        and provider.position_policy == "enter_and_close"
        and binds_signal_anchors(provider.execution, stop_anchor=True)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "Hulk short requires BTC-only 30m scope, its emitted short side, "
            "opposite-entry close, and no absolute target"
        )


def _validate_liquidity_sweep_long(provider: StrategyProviderConfig) -> None:
    valid = (
        provider.symbols == ("BTC",)
        and "long" in provider.sides
        and provider.timeframe == "1h"
        and provider.position_policy == "enter_and_close"
        and binds_signal_anchors(provider.execution, stop_anchor=False)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "liquidity-sweep long requires BTC-only 1h scope, its emitted long "
            "side, opposite-entry close, a fixed stop, and no absolute target"
        )
