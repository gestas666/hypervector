"""Reusable causal replay for the executable ETH pullback candidate."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.research.hype_breakout_entry_features import (
    build_hype_entry_features,
)
from hypervector.research.hype_breakout_entry_research import (
    HypeEntryPolicy,
    HypeEntryPolicyEvidence,
    apply_hype_entry_policy,
)
from hypervector.research.hype_breakout_exit_market import (
    HypeExitMarketEvidence,
    build_hype_exit_market,
)
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
    HypeExitReplayReport,
)
from hypervector.research.hype_breakout_exit_replay import (
    replay_hype_breakout_exits,
)

ETH_PULLBACK_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"


@dataclass(frozen=True)
class EthPullbackReplay:
    """Exact ETH replay plus source and policy coverage evidence."""

    report: HypeExitReplayReport
    market: pd.DataFrame
    market_evidence: HypeExitMarketEvidence
    policy_evidence: HypeEntryPolicyEvidence


def replay_eth_precompression_pullback(
    bars: pd.DataFrame,
    funding: pd.DataFrame,
) -> EthPullbackReplay:
    """Replay the live ETH entry, protection, cost, and hold contract."""
    market, market_evidence = build_hype_exit_market(bars, funding)
    features = build_hype_entry_features(market)
    entry_policy = HypeEntryPolicy(
        "precompression15_min40_pullback",
        require_nonpositive_body=True,
        maximum_prior_bbwp_min_15m=40.0,
    )
    filtered, policy_evidence = apply_hype_entry_policy(
        market,
        features,
        entry_policy,
    )
    config = HypeExitReplayConfig(
        stop_bps=60.0,
        maximum_hold_minutes=720,
        fee_bps_per_side=4.5,
        slippage_bps_per_side=2.0,
    )
    report = replay_hype_breakout_exits(
        filtered,
        HypeExitPolicy(ETH_PULLBACK_STRATEGY),
        config,
    )
    return EthPullbackReplay(report, filtered, market_evidence, policy_evidence)
