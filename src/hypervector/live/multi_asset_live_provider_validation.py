"""Provider-scope validation for the shared multi-asset live configuration."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from hypervector.live.btc_hulk_robust_short_provider import (
    HULK_ROBUST_SHORT_STRATEGY,
    HULK_SHORT_STRATEGIES,
)
from hypervector.live.btc_hulk_delayed_component_floor import (
    BTC_HULK_DELAYED_COMPONENT_POLICY_IDS,
)
from hypervector.live.btc_liquidity_sweep_long_provider import (
    LIQUIDITY_SWEEP_LONG_STRATEGIES,
    LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY,
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
    has_neutral_exit_modifiers,
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
from hypervector.live.v79_provider_validation import (
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
    execution = provider.execution
    valid = (
        provider.symbols == ("HYPE",)
        and provider.timeframe == "1m"
        and provider.execution_symbols in {(), ("HYPE",)}
        and execution.stop_policy == "fixed_bps"
        and execution.stop_bps == 80.0
        and execution.target_policy == "none"
        and execution.maximum_hold_seconds == 28_800
        and execution.maximum_hold_policy == "extend_while_regime_supported"
        and execution.hard_maximum_hold_seconds == 86_400
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "HYPE compression breakout requires HYPE-only 1m scope, an 80 bps "
            "stop, and the exact 8h-to-24h extension contract"
        )


def _validate_eth_transfer(provider: StrategyProviderConfig) -> None:
    execution = provider.execution
    valid = (
        provider.symbols == ("ETH",)
        and provider.timeframe == "1m"
        and provider.maximum_entry_delay_seconds == 60
        and provider.execution_symbols in {(), ("ETH",)}
        and provider.source_profile is None
        and provider.position_policy == "enter_and_close"
        and execution.stop_policy == "fixed_bps"
        and execution.stop_bps == 60.0
        and execution.target_policy == "none"
        and execution.maximum_hold_seconds == 43_200
        and execution.maximum_hold_policy == "fixed"
        and has_neutral_exit_modifiers(execution)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "ETH breakout transfer requires the 1m source timeframe, ETH-only "
            "observation, at most ETH-only execution authority, a 60 bps stop, "
            "and a 12-hour maximum hold"
        )


def _validate_range_onset(provider: StrategyProviderConfig) -> None:
    """Freeze the historical hourly-cross execution and fallback contract."""
    execution = provider.execution
    valid = (
        bool(provider.symbols)
        and set(provider.symbols).issubset({"BTC", "ETH", "SOL", "HYPE"})
        and provider.sides == _BOTH_SIDES
        and provider.timeframe == "1m"
        and provider.maximum_entry_delay_seconds == 60
        and execution.stop_policy == "fixed_bps"
        and execution.stop_bps == 60.0
        and execution.target_policy == "none"
        and execution.maximum_hold_seconds == 172_800
        and execution.hard_maximum_hold_seconds is None
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "range onset requires supported core symbols, both sides, 1m source "
            "polling, a 60 bps stop, opposite-cross exit, and 48h fallback"
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
    execution = provider.execution
    smart_floor = (
        provider.strategy_id == HULK_ROBUST_SHORT_STRATEGY
        and execution.profit_lock_policy in BTC_HULK_DELAYED_COMPONENT_POLICY_IDS
        and execution.provider_recipe_exit_policy == "ignore"
        and not execution.safety_stop_overlay
    )
    valid = (
        provider.symbols == ("BTC",)
        and provider.sides == frozenset({"short"})
        and provider.timeframe == "30m"
        and provider.maximum_entry_delay_seconds == 60
        and provider.execution_symbols in {(), ("BTC",)}
        and provider.position_policy == "enter_and_close"
        and execution.entry_liquidity == "taker_ioc"
        and execution.stop_policy == "structural_clamped_bps"
        and execution.minimum_stop_bps == 20.0
        and execution.maximum_stop_bps == 75.0
        and execution.target_policy == "reward_risk"
        and execution.target_r_multiple == 3.0
        and execution.maximum_hold_seconds == 86_400
        and execution.maximum_hold_policy == "fixed"
        and (has_neutral_exit_modifiers(execution) or smart_floor)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "robust Hulk short requires BTC-only 30m short scope, taker IOC, "
            "20-75 bps structural stop, 3R target, 24h maximum hold, and only "
            "the evidence-bound robust-v3 delayed component exit"
        )


def _validate_liquidity_sweep_long(provider: StrategyProviderConfig) -> None:
    execution = provider.execution
    expected_target = (
        60.0
        if provider.strategy_id == LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY
        else 26.666666666666668
    )
    expected_delay = (
        30 if provider.strategy_id == LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY else 60
    )
    valid = (
        provider.symbols == ("BTC",)
        and provider.sides == frozenset({"long"})
        and provider.timeframe == "1h"
        and provider.execution_symbols in {(), ("BTC",)}
        and provider.position_policy == "enter_and_close"
        and execution.entry_liquidity == "taker_ioc"
        and execution.stop_policy == "fixed_bps"
        and execution.stop_bps == 60.0
        and execution.target_policy == "fixed_bps"
        and execution.target_bps is not None
        and math.isclose(execution.target_bps, expected_target)
        and provider.maximum_entry_delay_seconds == expected_delay
        and execution.maximum_hold_seconds == 86_400
        and execution.maximum_hold_policy == "fixed"
        and has_neutral_exit_modifiers(execution)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "liquidity-sweep long requires exact BTC 1h long scope, "
            f"60/{expected_target:g} bps exits, {expected_delay}s delay, and 24h hold"
        )
