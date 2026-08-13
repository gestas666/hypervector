"""Frozen contract tests for the SOL breakout-continuation observer."""

from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_forward_experiments import (
    FORWARD_EXPERIMENT_NAMES,
    forward_experiment,
    source_authority_matches,
)


def test_sol_breakout_continuation_is_frozen_after_hypothesis_selection() -> None:
    experiment = forward_experiment("v14-sol-breakout-continuation-aligned-fixed")

    assert experiment.candidate_strategy_id == (
        "sol_breakout_continuation_aligned_fixed60_bidirectional_v1"
    )
    assert experiment.source_strategy_id == "hype_breakout_onset_bidirectional_v1"
    assert experiment.symbol == "SOL"
    assert experiment.blocker == "awaiting_new_5m_breakout_onset"
    assert experiment.cutoff_time_ms == 1_786_229_400_000
    assert experiment.funding_start_time_ms == 1_786_229_400_000
    assert experiment.source_stop_policy == "fixed_bps"
    assert experiment.source_stop_range_bps is None
    assert experiment.stop_proxy_bps == 80.0
    assert experiment.target_proxy_bps is None
    assert experiment.opi_cohort == "aligned"
    assert experiment.notional_usd == 75.0
    assert experiment.source_authority == "executable"


def test_sol_breakout_continuation_matches_v25_source_authority() -> None:
    experiment = forward_experiment("v14-sol-breakout-continuation-aligned-fixed")
    config = load_multi_asset_live_config(
        Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml"),
        mode="observe",
    )
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == experiment.source_strategy_id
    )

    assert source_authority_matches(experiment, provider.execution_symbols)
    assert provider.executable_sides("SOL") == frozenset({"long", "short"})
    assert "v14-sol-breakout-continuation-aligned-fixed" in FORWARD_EXPERIMENT_NAMES
