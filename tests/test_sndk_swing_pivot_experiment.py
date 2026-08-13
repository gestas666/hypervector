"""Frozen contract tests for the SNDK swing-pivot prospective observer."""

from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_forward_experiments import (
    FORWARD_EXPERIMENT_NAMES,
    forward_experiment,
    source_authority_matches,
)


def test_sndk_swing_pivot_is_frozen_after_hypothesis_selection() -> None:
    """The discovery path must be excluded from the prospective experiment."""
    experiment = forward_experiment("v15-sndk-swing-pivot-fixed")

    assert experiment.candidate_strategy_id == (
        "sndk_swing_pivot_relaxed_fixed60_bidirectional_v1"
    )
    assert experiment.source_strategy_id == (
        "hip3_swing_ha_sndk_gold_brent_bidirectional_v1"
    )
    assert experiment.symbol == "xyz:SNDK"
    assert experiment.blocker == "pivot_break_state_missing"
    assert experiment.cutoff_time_ms == 1_786_266_000_000
    assert experiment.funding_start_time_ms == 1_786_266_000_000
    assert experiment.source_stop_policy == "fixed_bps"
    assert experiment.source_stop_range_bps is None
    assert experiment.stop_proxy_bps == 80.0
    assert experiment.target_proxy_bps is None
    assert experiment.opi_cohort == "all"
    assert experiment.notional_usd == 75.0
    assert experiment.source_authority == "executable"


def test_sndk_swing_pivot_retains_both_side_v25_authority() -> None:
    """The observer must not narrow the source strategy to its discovery side."""
    experiment = forward_experiment("v15-sndk-swing-pivot-fixed")
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
    assert provider.executable_sides("xyz:SNDK") == frozenset({"long", "short"})
    assert "v15-sndk-swing-pivot-fixed" in FORWARD_EXPERIMENT_NAMES
