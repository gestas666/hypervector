"""Exact provider contract for the newly screened hourly price mechanisms."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hypervector.live.hourly_price_provider import (
    HOURLY_PRICE_SYMBOLS,
    PROTECTED_DONCHIAN20_STRATEGY,
    PROTECTED_DONCHIAN20_SYMBOLS,
)
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError

if TYPE_CHECKING:
    from hypervector.live.multi_asset_live_config import StrategyProviderConfig


def validate_hourly_price_provider(provider: StrategyProviderConfig) -> None:
    """Reject a mislabeled clock, side scope, or untested execution shape."""
    execution = provider.execution
    valid = (
        set(provider.symbols).issubset(HOURLY_PRICE_SYMBOLS)
        and provider.timeframe == "15m"
        and provider.maximum_entry_delay_seconds == 30
        and provider.sides == frozenset({"long", "short"})
        and provider.position_policy == "enter_and_close"
        and execution.entry_liquidity == "taker_ioc"
        and execution.stop_policy == "structural_clamped_bps"
        and execution.minimum_stop_bps == 20.0
        and execution.maximum_stop_bps == 250.0
        and execution.target_policy == "none"
        and execution.maximum_hold_seconds == 86400
        and execution.maximum_hold_policy == "fixed"
        and execution.provider_recipe_exit_policy == "honor"
        and _valid_profit_lock(provider)
        and not execution.safety_stop_overlay
        and not provider.execution_side_overrides
        and not provider.stop_bps_overrides
        and not provider.profit_lock_overrides
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "hourly price research requires qualified symbols, both sides, 15m source, "
            "30-second entry age, 20-250 bps structural stops, recipe exits, 24h fallback "
            "and the exact identity-bound profit-lock contract"
        )


def _valid_profit_lock(provider: StrategyProviderConfig) -> bool:
    execution = provider.execution
    if provider.strategy_id != PROTECTED_DONCHIAN20_STRATEGY:
        return execution.profit_lock_policy == "none"
    return (
        set(provider.symbols).issubset(PROTECTED_DONCHIAN20_SYMBOLS)
        and execution.profit_lock_policy == "completed_bar_trailing"
        and execution.profit_lock_activation_bps == 100.0
        and execution.profit_lock_floor_bps == 25.0
        and execution.profit_lock_giveback_bps == 50.0
    )
