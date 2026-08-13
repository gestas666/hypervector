"""Exact-diff contract for the inactive v31 Swing-pruned candidate."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hypervector.live.hip3_cohort_providers import HIP3_SWING_COMMODITY_STRATEGY
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_V25 = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")
_V31 = Path("configs/multi_asset_bidirectional_swing_pruned_candidate_v31.toml")
_V32 = Path(
    "configs/multi_asset_bidirectional_commodity_swing_retired_candidate_v32.toml"
)


def test_v31_changes_only_sndk_and_brent_swing_execution_authority() -> None:
    source = load_multi_asset_live_config(_V25, mode="observe")
    candidate = load_multi_asset_live_config(_V31, mode="observe")
    before = {provider.strategy_id: provider for provider in source.providers}
    after = {provider.strategy_id: provider for provider in candidate.providers}

    assert candidate.profile_id == (
        "multi_asset_bidirectional_swing_pruned_candidate_v31"
    )
    assert candidate.profile_fingerprint != source.profile_fingerprint
    assert candidate.maximum_positions == source.maximum_positions == 9
    assert candidate.margin_mode == source.margin_mode == "isolated"
    assert candidate.cohort_ledger == source.cohort_ledger
    assert candidate.stop_file == source.stop_file
    assert candidate.poll_seconds == source.poll_seconds
    assert candidate.lookback_days == source.lookback_days
    assert candidate.assets == tuple(
        replace(asset, parent_profile_id=candidate.profile_id)
        for asset in source.assets
    )
    assert set(after) == set(before)
    assert after[HIP3_SWING_COMMODITY_STRATEGY] == replace(
        before[HIP3_SWING_COMMODITY_STRATEGY],
        execution_symbols=("xyz:GOLD",),
    )
    for strategy in set(before) - {HIP3_SWING_COMMODITY_STRATEGY}:
        assert after[strategy] == before[strategy]

    removed = {
        (HIP3_SWING_COMMODITY_STRATEGY, "xyz:SNDK"),
        (HIP3_SWING_COMMODITY_STRATEGY, "xyz:BRENTOIL"),
    }
    assert candidate.executable_provider_symbols == (
        source.executable_provider_symbols - removed
    )


def test_v31_retains_observation_and_both_sides_for_every_asset() -> None:
    candidate = load_multi_asset_live_config(_V31, mode="observe")
    swing = next(
        provider
        for provider in candidate.providers
        if provider.strategy_id == HIP3_SWING_COMMODITY_STRATEGY
    )

    assert swing.symbols == ("xyz:SNDK", "xyz:GOLD", "xyz:BRENTOIL")
    assert swing.sides == frozenset({"long", "short"})
    assert swing.execution_symbols == ("xyz:GOLD",)
    assert all(
        asset.sides == frozenset({"long", "short"}) for asset in candidate.assets
    )


def test_v32_changes_only_gold_swing_execution_authority_from_v31() -> None:
    """The successor may retire GOLD Swing without changing another contract."""
    prior = load_multi_asset_live_config(_V31, mode="observe")
    candidate = load_multi_asset_live_config(_V32, mode="observe")
    before = {provider.strategy_id: provider for provider in prior.providers}
    after = {provider.strategy_id: provider for provider in candidate.providers}

    assert candidate.profile_id == (
        "multi_asset_bidirectional_commodity_swing_retired_candidate_v32"
    )
    assert candidate.profile_fingerprint != prior.profile_fingerprint
    assert candidate.assets == tuple(
        replace(asset, parent_profile_id=candidate.profile_id) for asset in prior.assets
    )
    assert after[HIP3_SWING_COMMODITY_STRATEGY] == replace(
        before[HIP3_SWING_COMMODITY_STRATEGY],
        execution_symbols=(),
    )
    for strategy in set(before) - {HIP3_SWING_COMMODITY_STRATEGY}:
        assert after[strategy] == before[strategy]
    assert candidate.executable_provider_symbols == (
        prior.executable_provider_symbols
        - {(HIP3_SWING_COMMODITY_STRATEGY, "xyz:GOLD")}
    )


def test_v32_observes_both_sides_of_retired_commodity_swing_route() -> None:
    """Removing order authority must not remove research telemetry."""
    candidate = load_multi_asset_live_config(_V32, mode="observe")
    swing = next(
        provider
        for provider in candidate.providers
        if provider.strategy_id == HIP3_SWING_COMMODITY_STRATEGY
    )

    assert swing.symbols == ("xyz:SNDK", "xyz:GOLD", "xyz:BRENTOIL")
    assert swing.sides == frozenset({"long", "short"})
    assert swing.execution_symbols == ()
