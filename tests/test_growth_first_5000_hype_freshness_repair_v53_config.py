"""Acceptance tests for the v53 HYPE maximum-hold evidence repair."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hypervector.live.hype_compression_alignment_provider import (
    HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
)
from hypervector.live.multi_asset_live_config import (
    StrategyProviderConfig,
    load_multi_asset_live_config,
)
from hypervector.research.cohort_configuration_generation import (
    load_configuration_expectation,
)

_V52 = Path("configs/multi_asset_growth_first_5000_evidence_bound_successor_v52.toml")
_V53 = Path("configs/multi_asset_growth_first_5000_hype_freshness_repair_v53.toml")
_PROFILE = "multi_asset_growth_first_5000_hype_freshness_repair_v53"
_FINGERPRINT = "f6378e473088b962724176f1b4aaf0857d4e2a6c3bf0103c2d1794d6bfd46a82"


def test_v53_changes_only_profile_identity_and_hype_evidence_freshness() -> None:
    """The technical repair cannot alter routes, sizing, or other exits."""
    prior = load_multi_asset_live_config(_V52, mode="observe")
    candidate = load_multi_asset_live_config(_V53, mode="observe")

    assert candidate.profile_id == _PROFILE
    assert candidate.profile_fingerprint == _FINGERPRINT
    assert candidate.profile_fingerprint != prior.profile_fingerprint
    assert candidate.symbols == prior.symbols
    assert candidate.maximum_positions == prior.maximum_positions
    assert candidate.executable_provider_directions == (
        prior.executable_provider_directions
    )
    assert (
        tuple(
            replace(asset, parent_profile_id=prior.profile_id)
            for asset in candidate.assets
        )
        == prior.assets
    )
    _assert_provider_delta(prior.providers, candidate.providers)


def test_v53_checkpoint_projection_exposes_the_freshness_contract() -> None:
    """The cockpit must expose the exact evidence age bound before cutover."""
    expectation = load_configuration_expectation(_V53)
    policies = {
        policy.strategy_id: policy for policy in expectation.provider_exit_policies
    }

    assert (
        policies[
            HYPE_COMPRESSION_ALIGNMENT_STRATEGY
        ].maximum_hold_evidence_maximum_age_seconds
        == 60
    )


def _assert_provider_delta(
    prior: tuple[StrategyProviderConfig, ...],
    candidate: tuple[StrategyProviderConfig, ...],
) -> None:
    assert len(candidate) == len(prior)
    for old, new in zip(prior, candidate, strict=True):
        if old.strategy_id != HYPE_COMPRESSION_ALIGNMENT_STRATEGY:
            assert new == old
            continue
        assert (
            replace(
                new,
                execution=replace(
                    new.execution,
                    maximum_hold_evidence_maximum_age_seconds=None,
                ),
            )
            == old
        )
        assert new.execution.maximum_hold_evidence_maximum_age_seconds == 60
