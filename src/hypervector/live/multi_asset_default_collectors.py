"""Concrete provider collector assembly for the multi-asset cohort."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Protocol

import pandas as pd

from hypervector.live import btc_structural_one_blocker_provider as btc_structural
from hypervector.live import btc_hulk_robust_short_provider as btc_hulk_short
from hypervector.live import btc_liquidity_sweep_long_provider as btc_sweep_long
from hypervector.live import eth_breakout_transfer_provider as eth_transfer
from hypervector.live import hype_breakout_cohort_provider as hype
from hypervector.live import hype_breakout_compression_provider as hype_compression
from hypervector.live import hype_breakout_retest_provider as hype_retest
from hypervector.live import hype_relaxed_one_blocker_provider as relaxed
from hypervector.live.hip3_cohort_providers import (
    HIP3_STRATEGIES,
    configured_hip3_collector,
)
from hypervector.live.hip3_fresh15_journal_provider import (
    HIP3_INDEX_FRESH15_V3_STRATEGY,
    Hip3Fresh15JournalCollector,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    StrategyProviderConfig,
)
from hypervector.live.multi_asset_market_bars import MultiAssetIntentPollerError
from hypervector.live.multi_asset_signal_source import (
    IntentBatch,
    collect_hulk_bidirectional_intents,
    collect_range_onset_bidirectional_intents,
)
from hypervector.live.sol_aligned_range_contract import (
    SOL_ALIGNED_RANGE_FIXED60_STRATEGY,
)
from hypervector.live.sol_aligned_range_one_blocker_provider import (
    SolAlignedRangeOneBlockerCollector,
)
from hypervector.live.source_follow_cohort_provider import (
    SOURCE_FOLLOW_COHORT_STRATEGY,
    configured_source_follow_collector,
)

_HULK_STRATEGY = "hulk_expansion_bidirectional_tuned_v2"
_RANGE_STRATEGY = "range_onset_bidirectional_v1"


class DefaultProviderCollectorProtocol(Protocol):
    """Structural collector type returned to the causal poller."""

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Evaluate one provider over completed source bars."""
        ...


def build_default_collector(
    provider: StrategyProviderConfig,
    config: MultiAssetLiveConfig,
    backtest_lab_root: Path,
) -> DefaultProviderCollectorProtocol:
    """Build the concrete collector declared by one validated provider."""
    strategy = provider.strategy_id
    collector = _lab_collector(strategy, backtest_lab_root)
    if collector is not None:
        return collector
    collector = _native_collector(provider, config)
    if collector is not None:
        return collector
    if strategy == HIP3_INDEX_FRESH15_V3_STRATEGY:
        return Hip3Fresh15JournalCollector()
    if strategy in HIP3_STRATEGIES:
        return configured_hip3_collector(
            strategy,
            asset_ledgers={asset.symbol: asset.live_ledger for asset in config.assets},
            cohort_ledger=config.cohort_ledger,
        )
    raise MultiAssetIntentPollerError(
        f"default collector is not defined for provider: {strategy}"
    )


def _lab_collector(
    strategy: str, backtest_lab_root: Path
) -> DefaultProviderCollectorProtocol | None:
    if strategy == _HULK_STRATEGY:
        _require_backtest_lab(backtest_lab_root)
        return partial(
            collect_hulk_bidirectional_intents,
            backtest_lab_root=backtest_lab_root,
        )
    if strategy == btc_hulk_short.HULK_ROBUST_SHORT_STRATEGY:
        _require_backtest_lab(backtest_lab_root)
        return btc_hulk_short.HulkRobustShortCollector(
            backtest_lab_root=backtest_lab_root,
        )
    return None


def _native_collector(
    provider: StrategyProviderConfig, config: MultiAssetLiveConfig
) -> DefaultProviderCollectorProtocol | None:
    strategy = provider.strategy_id
    if strategy in btc_sweep_long.LIQUIDITY_SWEEP_LONG_STRATEGIES:
        return btc_sweep_long.LiquiditySweepLongCollector(strategy_id=strategy)
    if strategy == _RANGE_STRATEGY:
        return partial(
            collect_range_onset_bidirectional_intents,
            entry_context_policies=dict(provider.entry_context_overrides),
        )
    if strategy == hype.HYPE_BREAKOUT_COHORT_STRATEGY:
        return hype.HypeBreakoutOnsetCollector()
    if strategy == hype_compression.HYPE_COMPRESSION_BREAKOUT_STRATEGY:
        return hype_compression.HypeCompressionBreakoutCollector(
            execution_enabled=(
                config.mode == "live" and "HYPE" in provider.execution_symbols
            )
        )
    if strategy == hype_retest.HYPE_BREAKOUT_RETEST_STRATEGY:
        return hype_retest.HypeBreakoutRetestCollector()
    if strategy == eth_transfer.ETH_BREAKOUT_TRANSFER_STRATEGY:
        return eth_transfer.EthBreakoutTransferCollector(
            execution_enabled=(
                config.mode == "live" and "ETH" in provider.execution_symbols
            )
        )
    if strategy == SOURCE_FOLLOW_COHORT_STRATEGY:
        collector = configured_source_follow_collector(config)
        if collector is None:
            raise MultiAssetIntentPollerError("source-follow collector is unavailable")
        return collector
    if strategy in relaxed.HYPE_RELAXED_ONE_BLOCKER_STRATEGIES:
        return relaxed.HypeRelaxedOneBlockerCollector(
            cohort_ledger=config.cohort_ledger,
            strategy_id=strategy,
        )
    if strategy == btc_structural.BTC_STRUCTURAL_FIXED60_STRATEGY:
        return btc_structural.BtcStructuralOneBlockerCollector(
            cohort_ledger=config.cohort_ledger,
        )
    if strategy == SOL_ALIGNED_RANGE_FIXED60_STRATEGY:
        return SolAlignedRangeOneBlockerCollector(
            cohort_ledger=config.cohort_ledger,
        )
    return None


def _require_backtest_lab(path: Path) -> None:
    if not path.is_dir():
        raise FileNotFoundError(f"backtest-lab dependency root not found: {path}")
