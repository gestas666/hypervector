"""Exact contracts for versioned multi-asset routes reused by successors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hypervector.live.hip3_cohort_providers import (
    HIP3_BREAKOUT_COMMODITY_FRESH15_STRATEGY,
)
from hypervector.live.hip3_fresh15_journal_provider import (
    HIP3_INDEX_FRESH15_V3_STRATEGY,
)
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError

if TYPE_CHECKING:
    from hypervector.live.cohort_execution_plan import ProviderExecutionContract
    from hypervector.live.multi_asset_live_config import StrategyProviderConfig


HULK_BIDIRECTIONAL_STRATEGY = "hulk_expansion_bidirectional_tuned_v2"
_BOTH_SIDES = frozenset({"long", "short"})


def has_neutral_exit_modifiers(execution: ProviderExecutionContract) -> bool:
    """Return whether no unversioned recipe, lock, or stop overlay is active."""
    return (
        not execution.safety_stop_overlay
        and execution.provider_recipe_exit_policy == "ignore"
        and execution.profit_lock_policy == "none"
    )


def validate_reused_route_contract(provider: StrategyProviderConfig) -> None:
    """Reject semantic drift under a known versioned provider identity."""
    if provider.strategy_id == HULK_BIDIRECTIONAL_STRATEGY:
        _validate_hulk_bidirectional(provider)
    elif provider.strategy_id == HIP3_BREAKOUT_COMMODITY_FRESH15_STRATEGY:
        _validate_commodity_fresh15(provider)
    elif provider.strategy_id == HIP3_INDEX_FRESH15_V3_STRATEGY:
        _validate_index_fresh15_v3(provider)


def _validate_hulk_bidirectional(provider: StrategyProviderConfig) -> None:
    execution = provider.execution
    valid = (
        bool(provider.symbols)
        and set(provider.symbols).issubset({"BTC", "ETH", "SOL", "HYPE"})
        and provider.sides == _BOTH_SIDES
        and provider.timeframe == "30m"
        and provider.maximum_entry_delay_seconds == 60
        and provider.position_policy == "enter_and_close"
        and execution.entry_liquidity == "taker_ioc"
        and execution.stop_policy == "structural_clamped_bps"
        and execution.minimum_stop_bps == 20.0
        and execution.maximum_stop_bps == 75.0
        and execution.target_policy == "reward_risk"
        and execution.target_r_multiple == 3.0
        and execution.maximum_hold_seconds == 86_400
        and execution.maximum_hold_policy == "fixed"
        and has_neutral_exit_modifiers(execution)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "bidirectional Hulk requires core-only 30m scope, taker IOC, "
            "20-75 bps structural stop, 3R target, and 24h maximum hold"
        )


def _validate_commodity_fresh15(provider: StrategyProviderConfig) -> None:
    valid_symbols = {"xyz:SNDK", "xyz:GOLD", "xyz:BRENTOIL"}
    if not (
        _valid_fresh15_base(provider, valid_symbols)
        and provider.execution.profit_lock_policy == "none"
    ):
        raise MultiAssetLiveConfigError(
            "fresh15 commodity breakout requires supported HIP-3 symbols, "
            "15m both-side scope, 30s entry delay, 80 bps stop, and 24h hold"
        )


def _validate_index_fresh15_v3(provider: StrategyProviderConfig) -> None:
    if not _valid_fresh15_base(provider, {"xyz:SP500", "xyz:SPCX"}):
        raise MultiAssetLiveConfigError(
            "fresh15 index v3 requires supported HIP-3 symbols, 15m both-side "
            "scope, 30s entry delay, 80 bps stop, and 24h hold"
        )
    execution = provider.execution
    no_lock = execution.profit_lock_policy == "none"
    trailing_lock = (
        execution.profit_lock_policy == "completed_bar_trailing"
        and execution.profit_lock_activation_bps == 100.0
        and execution.profit_lock_floor_bps == 40.0
        and execution.profit_lock_giveback_bps == 80.0
    )
    if not (no_lock or trailing_lock):
        raise MultiAssetLiveConfigError(
            "fresh15 index v3 permits no lock or the exact 100/40/80 lock"
        )


def _valid_fresh15_base(
    provider: StrategyProviderConfig,
    valid_symbols: set[str],
) -> bool:
    execution = provider.execution
    return (
        bool(provider.symbols)
        and set(provider.symbols).issubset(valid_symbols)
        and provider.sides == _BOTH_SIDES
        and provider.timeframe == "15m"
        and provider.maximum_entry_delay_seconds == 30
        and provider.position_policy == "enter_and_close"
        and execution.entry_liquidity == "taker_ioc"
        and execution.stop_policy == "fixed_bps"
        and execution.stop_bps == 80.0
        and execution.target_policy == "none"
        and execution.maximum_hold_seconds == 86_400
        and execution.maximum_hold_policy == "fixed"
        and execution.provider_recipe_exit_policy == "ignore"
        and not execution.safety_stop_overlay
    )
