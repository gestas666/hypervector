"""Frozen source-clock and startup-readiness requirements for live providers."""

from __future__ import annotations

from hypervector.live import btc_structural_one_blocker_provider as btc_structural
from hypervector.live.btc_hulk_robust_short_provider import (
    HULK_ROBUST_SHORT_STRATEGY,
)
from hypervector.live.btc_liquidity_sweep_long_provider import (
    LIQUIDITY_SWEEP_LONG_STRATEGY,
    LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY,
)
from hypervector.live import eth_breakout_transfer_provider as eth_transfer
from hypervector.live import hype_breakout_cohort_provider as hype
from hypervector.live import hype_breakout_compression_provider as hype_compression
from hypervector.live import hype_breakout_retest_provider as hype_retest
from hypervector.live import hype_relaxed_one_blocker_provider as relaxed
from hypervector.live.hip3_cohort_providers import HIP3_STRATEGIES
from hypervector.live.hip3_fresh15_journal_provider import (
    HIP3_INDEX_FRESH15_V3_STRATEGY,
)
from hypervector.live.sol_aligned_range_contract import (
    SOL_ALIGNED_RANGE_FIXED60_STRATEGY,
)
from hypervector.live.source_follow_cohort_provider import SOURCE_FOLLOW_COHORT_STRATEGY

HULK_STRATEGY = "hulk_expansion_bidirectional_tuned_v2"
RANGE_STRATEGY = "range_onset_bidirectional_v1"
SOURCE_TIMEFRAMES = {
    HULK_STRATEGY: "5m",
    HULK_ROBUST_SHORT_STRATEGY: "5m",
    LIQUIDITY_SWEEP_LONG_STRATEGY: "1m",
    LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY: "1m",
    RANGE_STRATEGY: "1m",
    SOURCE_FOLLOW_COHORT_STRATEGY: "1m",
    hype.HYPE_BREAKOUT_COHORT_STRATEGY: "1m",
    hype_compression.HYPE_COMPRESSION_BREAKOUT_STRATEGY: "1m",
    hype_retest.HYPE_BREAKOUT_RETEST_STRATEGY: "1m",
    eth_transfer.ETH_BREAKOUT_TRANSFER_STRATEGY: "1m",
    **{strategy: "1m" for strategy in relaxed.HYPE_RELAXED_ONE_BLOCKER_STRATEGIES},
    btc_structural.BTC_STRUCTURAL_FIXED60_STRATEGY: "1m",
    SOL_ALIGNED_RANGE_FIXED60_STRATEGY: "1m",
    **{strategy: "15m" for strategy in HIP3_STRATEGIES},
    HIP3_INDEX_FRESH15_V3_STRATEGY: "15m",
}
READINESS_SEED_LOOKBACK_MINUTES = {
    HULK_STRATEGY: 31,
    HULK_ROBUST_SHORT_STRATEGY: 31,
    LIQUIDITY_SWEEP_LONG_STRATEGY: 61,
    LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY: 61,
    RANGE_STRATEGY: 2,
    SOURCE_FOLLOW_COHORT_STRATEGY: 6,
    hype.HYPE_BREAKOUT_COHORT_STRATEGY: 2,
    hype_compression.HYPE_COMPRESSION_BREAKOUT_STRATEGY: 2,
    hype_retest.HYPE_BREAKOUT_RETEST_STRATEGY: 2,
    eth_transfer.ETH_BREAKOUT_TRANSFER_STRATEGY: 2,
    **{strategy: 2 for strategy in relaxed.HYPE_RELAXED_ONE_BLOCKER_STRATEGIES},
    btc_structural.BTC_STRUCTURAL_FIXED60_STRATEGY: 2,
    SOL_ALIGNED_RANGE_FIXED60_STRATEGY: 2,
    **{strategy: 16 for strategy in HIP3_STRATEGIES},
    HIP3_INDEX_FRESH15_V3_STRATEGY: 16,
}
