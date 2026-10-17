"""Acceptance contract for the V77 BTC component-exit repair."""

from __future__ import annotations

import pytest

from dataclasses import replace
from pathlib import Path

from hypervector.live.btc_hulk_delayed_component_floor import (
    BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY,
    BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY,
)
from hypervector.live.btc_hulk_robust_short_provider import (
    HULK_ROBUST_SHORT_STRATEGY,
)
from hypervector.live.cohort_profile_change_approval import (
    validate_profile_change_approval,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
)

_V76 = Path(
    "configs/multi_asset_growth_first_5000_"
    "seven_asset_validated_roster_candidate_v76.toml"
)
_V77 = Path(
    "configs/multi_asset_growth_first_5000_"
    "seven_asset_btc_component_exit_repair_v77.toml"
)
_PROFILE = "multi_asset_growth_first_5000_seven_asset_btc_component_exit_repair_v77"
_APPROVAL = Path(
    "docs/live-approvals/"
    "v76-to-v77-btc-component-exit-repair-approved-for-live-transition-20260901-v1.json"
)


def test_v77_changes_only_identity_approval_and_robust_v3_exit_policy() -> None:
    """V77 must preserve V76 except for the explicit versioned BTC repair."""
    baseline = _load(_V76)
    candidate = _load(_V77)
    old_robust = _provider(baseline, HULK_ROBUST_SHORT_STRATEGY)
    new_robust = _provider(candidate, HULK_ROBUST_SHORT_STRATEGY)

    assert candidate.profile_id == _PROFILE
    assert candidate.transition_approval == _APPROVAL
    assert candidate.symbols == (
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "ZEC",
        "xyz:SPCX",
        "xyz:SNDK",
    )
    assert new_robust.execution.profit_lock_policy == (
        BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY.policy_id
    )
    assert old_robust.execution.profit_lock_policy == (
        BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY.policy_id
    )
    assert new_robust == replace(
        old_robust,
        execution=replace(
            old_robust.execution,
            profit_lock_policy=BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY.policy_id,
        ),
    )
    assert _normalized(candidate, baseline, old_robust) == baseline


@pytest.mark.evidence
def test_v77_transition_approval_matches_candidate_and_evidence() -> None:
    """V77 approval must bind the exact transition and evidence digest."""
    baseline = _load(_V76)
    candidate = _load(_V77)

    evidence = validate_profile_change_approval(
        baseline,
        candidate,
        candidate.transition_approval,
    )

    assert evidence["approval_status"] == "approved_for_live_transition"


def _load(path: Path) -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(
        path,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )


def _provider(config: MultiAssetLiveConfig, strategy_id: str) -> StrategyProviderConfig:
    return next(row for row in config.providers if row.strategy_id == strategy_id)


def _normalized(
    candidate: MultiAssetLiveConfig,
    baseline: MultiAssetLiveConfig,
    old_robust: StrategyProviderConfig,
) -> MultiAssetLiveConfig:
    return replace(
        candidate,
        profile_id=baseline.profile_id,
        source_path=baseline.source_path,
        transition_approval=baseline.transition_approval,
        assets=tuple(
            replace(asset, parent_profile_id=baseline.profile_id)
            for asset in candidate.assets
        ),
        providers=tuple(
            old_robust if row.strategy_id == HULK_ROBUST_SHORT_STRATEGY else row
            for row in candidate.providers
        ),
    )
