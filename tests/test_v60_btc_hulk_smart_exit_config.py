"""Acceptance contract for the V60 BTC Hulk smart-exit successor."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live.btc_hulk_delayed_component_floor import (
    BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY,
)
from hypervector.live.btc_hulk_robust_short_provider import (
    HULK_ROBUST_SHORT_STRATEGY,
    HULK_TUNED_SHORT_STRATEGY,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
    validate_multi_asset_live_config,
)
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError

_V59 = Path(
    "configs/"
    "multi_asset_growth_first_5000_eight_asset_sp500_short_containment_candidate_v59.toml"
)
_V60 = Path(
    "configs/"
    "multi_asset_growth_first_5000_eight_asset_btc_hulk_smart_exit_candidate_v60.toml"
)
_PROFILE = "multi_asset_growth_first_5000_eight_asset_btc_hulk_smart_exit_candidate_v60"


def test_v60_changes_only_profile_and_robust_hulk_profit_protection() -> None:
    """V60 must preserve V59 except for the evidence-bound robust-v3 floor."""
    baseline = _load(_V59)
    candidate = _load(_V60)
    old_robust = _provider(baseline, HULK_ROBUST_SHORT_STRATEGY)
    new_robust = _provider(candidate, HULK_ROBUST_SHORT_STRATEGY)

    assert candidate.profile_id == _PROFILE
    normalized = replace(
        candidate,
        profile_id=baseline.profile_id,
        source_path=baseline.source_path,
        assets=tuple(
            replace(asset, parent_profile_id=baseline.profile_id)
            for asset in candidate.assets
        ),
        providers=baseline.providers,
    )
    assert normalized == baseline
    assert new_robust == replace(
        old_robust,
        execution=replace(
            old_robust.execution,
            profit_lock_policy=BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY.policy_id,
        ),
    )
    assert tuple(row for row in candidate.providers if row != new_robust) == tuple(
        row for row in baseline.providers if row != old_robust
    )


def test_v60_does_not_apply_the_robust_v3_floor_to_tuned_v2() -> None:
    """The strategy-specific policy must fail closed on the tuned-v2 route."""
    candidate = _load(_V60)
    tuned = _provider(candidate, HULK_TUNED_SHORT_STRATEGY)
    assert tuned.execution.profit_lock_policy == "none"

    providers = tuple(
        replace(
            row,
            execution=replace(
                row.execution,
                profit_lock_policy=BTC_HULK_DELAYED_COMPONENT_FLOOR_POLICY.policy_id,
            ),
        )
        if row.strategy_id == HULK_TUNED_SHORT_STRATEGY
        else row
        for row in candidate.providers
    )
    with pytest.raises(MultiAssetLiveConfigError, match="robust Hulk short"):
        validate_multi_asset_live_config(replace(candidate, providers=providers))


def _load(path: Path) -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(
        path,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )


def _provider(config: MultiAssetLiveConfig, strategy_id: str) -> StrategyProviderConfig:
    return next(row for row in config.providers if row.strategy_id == strategy_id)
