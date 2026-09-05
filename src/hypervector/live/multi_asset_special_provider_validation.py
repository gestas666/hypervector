"""Exact contracts for specialized multi-asset strategy providers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hypervector.live.hype_native_breakout_provider import (
    HYPE_NATIVE_BREAKOUT_LONG_STRATEGY,
)
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError
from hypervector.live.multi_asset_route_contract_validation import (
    has_neutral_exit_modifiers,
)

if TYPE_CHECKING:
    from hypervector.live.cohort_execution_plan import ProviderExecutionContract
    from hypervector.live.multi_asset_live_config import StrategyProviderConfig

_BOTH_SIDES = frozenset({"long", "short"})


def validate_research_pending_market_observer(
    provider: StrategyProviderConfig,
) -> None:
    """Keep data-only roster coverage structurally execution-disabled."""
    execution = provider.execution
    valid = (
        bool(provider.symbols)
        and provider.sides == _BOTH_SIDES
        and provider.timeframe == "15m"
        and provider.maximum_entry_delay_seconds == 30
        and provider.execution_symbols == ()
        and provider.position_policy == "enter_and_close"
        and execution.entry_liquidity == "taker_ioc"
        and execution.stop_policy == "fixed_bps"
        and execution.stop_bps == 80.0
        and execution.target_policy == "none"
        and execution.maximum_hold_seconds == 86_400
        and has_neutral_exit_modifiers(execution)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "research-pending market observer must be both-side, 15m, and "
            "execution-disabled with a neutral fallback contract"
        )


def validate_spcx_cash_open(provider: StrategyProviderConfig) -> None:
    """Require the exact frozen SPCX cash-open execution contract."""
    execution = provider.execution
    valid = (
        provider.symbols == ("xyz:SPCX",)
        and provider.sides == _BOTH_SIDES
        and provider.timeframe == "15m"
        and provider.maximum_entry_delay_seconds == 30
        and provider.execution_symbols == ("xyz:SPCX",)
        and provider.position_policy == "enter_and_close"
        and execution.entry_liquidity == "taker_ioc"
        and execution.stop_policy == "fixed_bps"
        and execution.stop_bps == 80.0
        and execution.target_policy == "absolute_anchor"
        and execution.maximum_hold_seconds == 22_500
        and execution.maximum_hold_policy == "fixed"
        and execution.provider_recipe_exit_policy == "honor"
        and execution.profit_lock_policy == "none"
        and not execution.safety_stop_overlay
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "SPCX cash-open requires exact 15m both-side scope, absolute target, "
            "80 bps stop, 25-bar hold, and recipe-authoritative exits"
        )


def validate_hype_native_breakout(provider: StrategyProviderConfig) -> None:
    """Require the exact HYPE native-breakout authority and exit contract."""
    execution = provider.execution
    long_only = provider.strategy_id == HYPE_NATIVE_BREAKOUT_LONG_STRATEGY
    expected_sides = frozenset({"long"}) if long_only else _BOTH_SIDES
    expected_recipe_exit = "honor" if long_only else "ignore"
    valid = (
        provider.symbols == ("HYPE",)
        and provider.sides == _BOTH_SIDES
        and provider.timeframe == "1m"
        and provider.maximum_entry_delay_seconds == 60
        and provider.execution_symbols in {(), ("HYPE",)}
        and provider.executable_sides("HYPE") == expected_sides
        and provider.position_policy == "enter_and_close"
        and execution.stop_policy == "fixed_bps"
        and execution.stop_bps == 80.0
        and execution.target_policy == "none"
        and execution.maximum_hold_seconds == 28_800
        and execution.maximum_hold_policy == "fixed"
        and execution.hard_maximum_hold_seconds is None
        and execution.maximum_hold_evidence_maximum_age_seconds is None
        and execution.provider_recipe_exit_policy == expected_recipe_exit
    )
    if not valid:
        authority = "long-authority" if long_only else "bidirectional-authority"
        raise MultiAssetLiveConfigError(
            f"native breakout-onset {authority} requires HYPE-only 1m scope, "
            "an 80 bps stop, opposite-onset close, and an exact fixed 8h hold"
        )


def validate_hype_compression_alignment(provider: StrategyProviderConfig) -> None:
    """Require the frozen HYPE alignment route and bounded hold extension."""
    execution = provider.execution
    execution_sides = provider.executable_sides("HYPE")
    valid_recipe_exit = execution.provider_recipe_exit_policy == "ignore" or (
        len(execution_sides) == 1 and execution.provider_recipe_exit_policy == "honor"
    )
    valid = (
        provider.symbols == ("HYPE",)
        and provider.sides == _BOTH_SIDES
        and provider.timeframe == "1m"
        and provider.maximum_entry_delay_seconds == 60
        and provider.execution_symbols in {(), ("HYPE",)}
        and provider.position_policy == "enter_and_close"
        and execution.entry_liquidity == "taker_ioc"
        and execution.stop_policy == "fixed_bps"
        and execution.stop_bps == 80.0
        and execution.target_policy == "none"
        and execution.maximum_hold_seconds == 28_800
        and execution.maximum_hold_policy == "extend_while_regime_supported"
        and execution.hard_maximum_hold_seconds == 86_400
        and execution.maximum_hold_evidence_maximum_age_seconds in {None, 60}
        and valid_recipe_exit
        and _valid_hype_alignment_profit_lock(execution)
        and not execution.safety_stop_overlay
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "HYPE compression alignment breakout requires HYPE-only both-side "
            "1m scope, an 80 bps stop, and the exact fresh 8h-to-24h extension "
            "contract"
        )


def _valid_hype_alignment_profit_lock(
    execution: ProviderExecutionContract,
) -> bool:
    if execution.profit_lock_policy == "none":
        return True
    return (
        execution.profit_lock_policy == "completed_bar_trailing"
        and execution.profit_lock_activation_bps == 60.0
        and execution.profit_lock_floor_bps == 15.0
        and execution.profit_lock_giveback_bps == 30.0
    )
