"""Concrete provider collector assembly for the multi-asset cohort."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Protocol

import pandas as pd

from hypervector.data.event_archive import EventArchive
from hypervector.live import btc_structural_one_blocker_provider as btc_structural
from hypervector.live import btc_hulk_robust_short_provider as btc_hulk_short
from hypervector.live import btc_liquidity_sweep_long_provider as btc_sweep_long
from hypervector.live import directional_range_onset_provider as directional_range
from hypervector.live import eth_breakout_transfer_provider as eth_transfer
from hypervector.live import hype_breakout_cohort_provider as hype
from hypervector.live import hype_native_breakout_provider as hype_native
from hypervector.live import hype_compression_alignment_provider as hype_alignment
from hypervector.live import hype_breakout_compression_provider as hype_compression
from hypervector.live import hype_breakout_retest_provider as hype_retest
from hypervector.live import hype_relaxed_one_blocker_provider as relaxed
from hypervector.live.hip3_cohort_providers import (
    HIP3_STRATEGIES,
    configured_hip3_collector,
)
from hypervector.live.hip3_fresh15_journal_provider import (
    HIP3_INDEX_FRESH15_V3_STRATEGY,
    HIP3_SNDK_FRESH15_V4_STRATEGY,
    Hip3Fresh15JournalCollector,
)
from hypervector.live.hip3_cash_open_gap_provider import (
    HIP3_SPCX_CASH_OPEN_STRATEGY,
    Hip3CashOpenGapCollector,
)
from hypervector.live.hip3_cash_open_trade_source import (
    SPCX_CAPTURE_START_MS,
    Hip3CashOpenTradeBarSource,
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
from hypervector.live.research_pending_market_observer import (
    RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY,
    ResearchPendingMarketObserverCollector,
)
from hypervector.live.sol_aligned_range_contract import (
    SOL_ALIGNED_RANGE_FIXED60_STRATEGY,
)
from hypervector.live.sol_aligned_range_one_blocker_provider import (
    SolAlignedRangeOneBlockerCollector,
)
from hypervector.live.spcx_cash_session_breakout_provider import (
    SPCX_CASH_SESSION_LONG_STRATEGY,
    SpcxCashSessionBreakoutCollector,
)
from hypervector.live.zec_donchian_provider import (
    ZEC_DONCHIAN_LONG_STRATEGY,
    ZecDonchianLongCollector,
)
from hypervector.live.hourly_price_provider import (
    HOURLY_PRICE_STRATEGIES,
    HourlyPriceCollector,
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
    if strategy in HOURLY_PRICE_STRATEGIES:
        return HourlyPriceCollector(strategy_id=strategy)
    collector = _lab_collector(strategy, backtest_lab_root)
    if collector is not None:
        return collector
    collector = _native_collector(provider, config)
    if collector is not None:
        return collector
    if strategy in {HIP3_INDEX_FRESH15_V3_STRATEGY, HIP3_SNDK_FRESH15_V4_STRATEGY}:
        return Hip3Fresh15JournalCollector()
    if strategy == HIP3_SPCX_CASH_OPEN_STRATEGY:
        archive = EventArchive(
            data_root=config.cohort_ledger.parents[2],
            symbol="xyz:SPCX",
            batch_size=2_000,
        )
        return Hip3CashOpenGapCollector(
            source=Hip3CashOpenTradeBarSource(
                archive=archive,
                symbol="xyz:SPCX",
                capture_start_ms=SPCX_CAPTURE_START_MS,
            )
        )
    if strategy == RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY:
        return ResearchPendingMarketObserverCollector()
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
    if strategy in btc_hulk_short.HULK_SHORT_STRATEGIES:
        _require_backtest_lab(backtest_lab_root)
        return btc_hulk_short.HulkRobustShortCollector(
            backtest_lab_root=backtest_lab_root,
            strategy_id=strategy,
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
    hype_collector = _hype_collector(provider, config)
    if hype_collector is not None:
        return hype_collector
    if strategy == eth_transfer.ETH_BREAKOUT_TRANSFER_STRATEGY:
        return eth_transfer.EthBreakoutTransferCollector(
            execution_enabled=(
                config.mode == "live" and "ETH" in provider.execution_symbols
            )
        )
    if strategy == btc_structural.BTC_STRUCTURAL_FIXED60_STRATEGY:
        return btc_structural.BtcStructuralOneBlockerCollector(
            cohort_ledger=config.cohort_ledger,
        )
    if strategy == SOL_ALIGNED_RANGE_FIXED60_STRATEGY:
        return SolAlignedRangeOneBlockerCollector(
            cohort_ledger=config.cohort_ledger,
        )
    if strategy in {
        directional_range.ETH_RANGE_LONG_STRATEGY,
        directional_range.SOL_RANGE_SHORT_STRATEGY,
    }:
        return directional_range.DirectionalRangeOnsetCollector(
            strategy_id=strategy,
        )
    if strategy == ZEC_DONCHIAN_LONG_STRATEGY:
        return ZecDonchianLongCollector()
    if strategy == SPCX_CASH_SESSION_LONG_STRATEGY:
        return SpcxCashSessionBreakoutCollector(
            source_collector=Hip3Fresh15JournalCollector()
        )
    return None


def _hype_collector(
    provider: StrategyProviderConfig, config: MultiAssetLiveConfig
) -> DefaultProviderCollectorProtocol | None:
    strategy = provider.strategy_id
    if strategy == hype.HYPE_BREAKOUT_COHORT_STRATEGY:
        return hype.HypeBreakoutOnsetCollector()
    if strategy in {
        hype_native.HYPE_NATIVE_BREAKOUT_STRATEGY,
        hype_native.HYPE_NATIVE_BREAKOUT_LONG_STRATEGY,
    }:
        return hype_native.HypeNativeBreakoutOnsetCollector(
            strategy_id=strategy,
            entry_sides=provider.executable_sides("HYPE"),
        )
    if strategy == hype_compression.HYPE_COMPRESSION_BREAKOUT_STRATEGY:
        return hype_compression.HypeCompressionBreakoutCollector(
            execution_enabled=(
                config.mode == "live" and "HYPE" in provider.execution_symbols
            )
        )
    if strategy == hype_alignment.HYPE_COMPRESSION_ALIGNMENT_STRATEGY:
        return hype_alignment.HypeCompressionAlignmentCollector(
            execution_enabled=(
                config.mode == "live" and "HYPE" in provider.execution_symbols
            ),
            execution_sides=provider.executable_sides("HYPE"),
        )
    if strategy == hype_retest.HYPE_BREAKOUT_RETEST_STRATEGY:
        return hype_retest.HypeBreakoutRetestCollector()
    if strategy in relaxed.HYPE_RELAXED_ONE_BLOCKER_STRATEGIES:
        return relaxed.HypeRelaxedOneBlockerCollector(
            cohort_ledger=config.cohort_ledger,
            strategy_id=strategy,
        )
    return None


def _require_backtest_lab(path: Path) -> None:
    if not path.is_dir():
        raise FileNotFoundError(f"backtest-lab dependency root not found: {path}")
