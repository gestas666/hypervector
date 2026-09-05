"""Journal-selected production recipes for the staged HIP-3 providers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from hypervector.live.hip3_cohort_providers import (
    HIP3_BREAKOUT_COMMODITY_STRATEGY,
    HIP3_BREAKOUT_COMMODITY_FRESH15_STRATEGY,
    HIP3_BREAKOUT_INDEX_STRATEGY,
    HIP3_BREAKOUT_INDEX_FRESH15_STRATEGY,
    HIP3_BREAKOUT_SNDK_FRESH15_STRATEGY,
    HIP3_SWING_COMMODITY_STRATEGY,
    HIP3_SWING_INDEX_STRATEGY,
    Hip3BreakoutPressureCollector,
    Hip3SwingHaCollector,
)
from hypervector.live.hip3_ledger_pressure import Hip3LedgerPressureSource
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.swing_ha_signals import SwingHaSignalConfig


def configured_hip3_recipe(
    strategy_id: str,
) -> SwingHaSignalConfig | Hip3BreakoutPressureConfig:
    """Return the exact journal-selected recipe used by the live collector."""
    if strategy_id == HIP3_SWING_INDEX_STRATEGY:
        return _swing_config(index_group=True)
    if strategy_id == HIP3_SWING_COMMODITY_STRATEGY:
        return _swing_config(index_group=False)
    if strategy_id in {
        HIP3_BREAKOUT_INDEX_STRATEGY,
        HIP3_BREAKOUT_INDEX_FRESH15_STRATEGY,
    }:
        return Hip3BreakoutPressureConfig(32, 21, 55, 0.1, 120.0)
    if strategy_id in {
        HIP3_BREAKOUT_COMMODITY_STRATEGY,
        HIP3_BREAKOUT_COMMODITY_FRESH15_STRATEGY,
        HIP3_BREAKOUT_SNDK_FRESH15_STRATEGY,
    }:
        return Hip3BreakoutPressureConfig(32, 21, 55, 0.35, 120.0)
    raise ValueError(f"unsupported HIP-3 provider: {strategy_id}")


def configured_hip3_collector(
    strategy_id: str,
    *,
    asset_ledgers: Mapping[str, Path],
    cohort_ledger: Path,
) -> Hip3SwingHaCollector | Hip3BreakoutPressureCollector:
    """Resolve one exact strategy identity to its frozen research recipe."""
    recipe = configured_hip3_recipe(strategy_id)
    if isinstance(recipe, SwingHaSignalConfig):
        return Hip3SwingHaCollector(
            strategy_id=strategy_id,
            config=recipe,
        )
    source = Hip3LedgerPressureSource(
        asset_ledgers=asset_ledgers,
        cohort_ledger=cohort_ledger,
    )
    return Hip3BreakoutPressureCollector(
        strategy_id=strategy_id,
        config=recipe,
        pressure_source=source,
    )


def _swing_config(*, index_group: bool) -> SwingHaSignalConfig:
    return SwingHaSignalConfig(
        fast_ema=50,
        slow_ema=200,
        pivot_length=8,
        entry_mode="state" if index_group else "onset",
        exit_mode="alignment_loss" if index_group else "ha_flip",
        order_block_role="agreement",
        order_block_periods=5 if index_group else 3,
        order_block_minimum_move_pct=0.5,
    )
