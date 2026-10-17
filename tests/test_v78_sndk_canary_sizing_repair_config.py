"""Acceptance contract for the V78 SNDK canary-sizing repair."""

from __future__ import annotations

import pytest

from dataclasses import replace
from pathlib import Path

from hypervector.live.cohort_profile_change_approval import (
    validate_profile_change_approval,
)
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

_V77 = Path(
    "configs/multi_asset_growth_first_5000_"
    "seven_asset_btc_component_exit_repair_v77.toml"
)
_V78 = Path(
    "configs/multi_asset_growth_first_5000_"
    "seven_asset_sndk_canary_sizing_repair_v78.toml"
)
_PROFILE = "multi_asset_growth_first_5000_seven_asset_sndk_canary_sizing_repair_v78"
_APPROVAL = Path(
    "docs/live-approvals/"
    "v77-to-v78-sndk-canary-sizing-repair-approved-for-live-transition-20260902-v1.json"
)


def test_v78_changes_only_identity_approval_and_sndk_sizing() -> None:
    """V78 must preserve V77 except for the explicit SNDK exposure repair."""
    baseline = _load(_V77)
    candidate = _load(_V78)
    old_sndk = _asset(baseline, "xyz:SNDK")
    new_sndk = _asset(candidate, "xyz:SNDK")

    assert candidate.profile_id == _PROFILE
    assert candidate.transition_approval == _APPROVAL
    assert candidate.symbols == baseline.symbols
    assert candidate.providers == baseline.providers
    assert candidate.executable_provider_directions == (
        baseline.executable_provider_directions
    )
    assert new_sndk == replace(
        old_sndk,
        parent_profile_id=_PROFILE,
        margin_fraction=0.03,
        max_notional_usd=750.0,
    )
    assert _planned_notional(new_sndk, equity_usd=5_000.0) == 750.0
    assert _normalized(candidate, baseline, old_sndk) == baseline


@pytest.mark.evidence
def test_v78_transition_approval_matches_candidate_and_evidence() -> None:
    """V78 approval must bind the exact transition and evidence digest."""
    baseline = _load(_V77)
    candidate = _load(_V78)

    evidence = validate_profile_change_approval(
        baseline,
        candidate,
        candidate.transition_approval,
    )

    assert evidence["approval_status"] == "approved_for_live_transition"
    assert evidence["retired_execution_scopes"] == []


def _load(path: Path) -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(
        path,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )


def _asset(config: MultiAssetLiveConfig, symbol: str) -> AssetLiveConfig:
    return next(row for row in config.assets if row.symbol == symbol)


def _planned_notional(asset: AssetLiveConfig, *, equity_usd: float) -> float:
    return min(
        equity_usd * asset.margin_fraction * asset.leverage,
        asset.max_notional_usd,
    )


def _normalized(
    candidate: MultiAssetLiveConfig,
    baseline: MultiAssetLiveConfig,
    old_sndk: AssetLiveConfig,
) -> MultiAssetLiveConfig:
    return replace(
        candidate,
        profile_id=baseline.profile_id,
        source_path=baseline.source_path,
        transition_approval=baseline.transition_approval,
        assets=tuple(
            old_sndk
            if row.symbol == old_sndk.symbol
            else replace(row, parent_profile_id=baseline.profile_id)
            for row in candidate.assets
        ),
    )
