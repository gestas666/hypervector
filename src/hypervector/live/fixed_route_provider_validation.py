"""Exact execution contracts for the directional range, ZEC and SPCX routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hypervector.live.directional_range_onset_provider import (
    ETH_RANGE_LONG_STRATEGY,
)
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError

if TYPE_CHECKING:
    from hypervector.live.multi_asset_live_config import StrategyProviderConfig

_BOTH_SIDES = frozenset({"long", "short"})


def validate_directional_range(provider: StrategyProviderConfig) -> None:
    """Freeze directional range entry, opposite-onset exit, and fallback."""
    expected = (
        ("ETH", "long")
        if provider.strategy_id == ETH_RANGE_LONG_STRATEGY
        else ("SOL", "short")
    )
    symbol, side = expected
    execution = provider.execution
    valid = (
        provider.symbols == (symbol,)
        and provider.sides == _BOTH_SIDES
        and provider.timeframe == "1m"
        and provider.maximum_entry_delay_seconds == 60
        and provider.execution_symbols in ((), (symbol,))
        and provider.executable_sides(symbol) == frozenset({side})
        and provider.position_policy == "enter_and_close"
        and execution.entry_liquidity == "taker_ioc"
        and execution.stop_policy == "fixed_bps"
        and execution.stop_bps == 60.0
        and execution.target_policy == "none"
        and execution.maximum_hold_seconds == 172_800
        and execution.maximum_hold_policy == "fixed"
        and execution.provider_recipe_exit_policy == "honor"
        and execution.profit_lock_policy == "none"
        and not execution.safety_stop_overlay
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "directional range routes require optional ETH-long or SOL-short 1m "
            "authority, a 60 bps stop, opposite-onset exit, and 48h fallback"
        )


def validate_zec_donchian_long(provider: StrategyProviderConfig) -> None:
    """Freeze ZEC observation and optional long probation authority."""
    execution = provider.execution
    execution_scope = provider.execution_symbols
    valid_authority = execution_scope == () or (
        execution_scope == ("ZEC",)
        and provider.executable_sides("ZEC") == frozenset({"long"})
    )
    valid = (
        provider.symbols == ("ZEC",)
        and provider.sides == _BOTH_SIDES
        and provider.timeframe == "15m"
        and provider.maximum_entry_delay_seconds == 30
        and valid_authority
        and provider.position_policy == "enter_and_close"
        and execution.entry_liquidity == "taker_ioc"
        and execution.stop_policy == "structural_clamped_bps"
        and execution.minimum_stop_bps == 20.0
        and execution.maximum_stop_bps == 250.0
        and execution.target_policy == "none"
        and execution.maximum_hold_seconds == 2_592_000
        and execution.maximum_hold_policy == "fixed"
        and execution.provider_recipe_exit_policy == "honor"
        and execution.profit_lock_policy == "none"
        and not execution.safety_stop_overlay
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "ZEC Donchian requires exact 15m observation, optional long-only "
            "authority, a 20-250 bps structural stop, ten-bar exit, and 30-day "
            "fallback"
        )


def validate_spcx_cash_session_long(provider: StrategyProviderConfig) -> None:
    """Freeze the low-confidence SPCX cash-session probation contract."""
    execution = provider.execution
    valid = (
        provider.symbols == ("xyz:SPCX",)
        and provider.sides == _BOTH_SIDES
        and provider.timeframe == "15m"
        and provider.maximum_entry_delay_seconds == 30
        and provider.execution_symbols == ("xyz:SPCX",)
        and provider.executable_sides("xyz:SPCX") == frozenset({"long"})
        and provider.position_policy == "enter_and_close"
        and execution.entry_liquidity == "taker_ioc"
        and execution.stop_policy == "fixed_bps"
        and execution.stop_bps == 60.0
        and execution.target_policy == "fixed_bps"
        and execution.target_bps == 120.0
        and execution.maximum_hold_seconds == 22_500
        and execution.maximum_hold_policy == "fixed"
        and execution.provider_recipe_exit_policy == "honor"
        and execution.profit_lock_policy == "none"
        and not execution.safety_stop_overlay
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "SPCX cash-session probation requires exact 15m long authority, "
            "a 60 bps stop, 120 bps target, session-close exit, and fallback"
        )
