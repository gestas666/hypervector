"""Acceptance contract for the operator-approved V64 GOLD asset removal."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hypervector.live.cohort_profile_change_approval import (
    validate_profile_change_approval,
)
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
)

_V63 = Path(
    "configs/"
    "multi_asset_growth_first_5000_nine_asset_bankroll_builder_candidate_v63.toml"
)
_V64 = Path(
    "configs/multi_asset_growth_first_5000_eight_asset_gold_removed_candidate_v64.toml"
)
_APPROVAL = Path(
    "docs/live-approvals/"
    "v63-to-v64-gold-removal-approved-for-live-transition-20260901-v1.json"
)
_PROFILE = "multi_asset_growth_first_5000_eight_asset_gold_removed_candidate_v64"
_HIP3 = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"


def test_v64_removes_only_gold_and_transition_metadata() -> None:
    """V64 must preserve every V63 contract except GOLD and transition identity."""
    baseline = _load(_V63)
    candidate = _load(_V64)
    old_provider = _provider(baseline, _HIP3)
    new_provider = _provider(candidate, _HIP3)
    gold = next(asset for asset in baseline.assets if asset.symbol == "xyz:GOLD")

    assert candidate.profile_id == _PROFILE
    assert candidate.transition_approval == _APPROVAL
    assert candidate.symbols == baseline.symbols[:-1]
    assert new_provider == replace(
        old_provider,
        symbols=("xyz:SNDK", "xyz:BRENTOIL"),
        execution_symbols=("xyz:SNDK", "xyz:BRENTOIL"),
    )
    assert _restore_v63(candidate, baseline, gold, old_provider) == baseline


def test_v64_has_eight_assets_and_twenty_three_executable_directions() -> None:
    """GOLD must be absent from asset and executable-provider authority."""
    candidate = _load(_V64)

    assert len(candidate.assets) == 8
    assert len(candidate.executable_provider_directions) == 23
    assert "xyz:GOLD" not in candidate.symbols
    assert all(
        symbol != "xyz:GOLD"
        for _, symbol, _ in candidate.executable_provider_directions
    )


def test_v64_transition_approval_records_terminal_gold_removal() -> None:
    """The exact V63-to-V64 approval must retire both GOLD directions."""
    baseline = _load(_V63)
    candidate = _load(_V64)

    evidence = validate_profile_change_approval(
        baseline,
        candidate,
        candidate.transition_approval,
    )

    assert evidence["state"] == "approved_profile_change"
    assert evidence["retired_execution_scopes"] == [
        f"{_HIP3}|xyz:GOLD|long",
        f"{_HIP3}|xyz:GOLD|short",
    ]
    assert evidence["replacement_execution_scopes"] == []
    assert evidence["execution_authority"] == "none"


def _load(source: Path) -> MultiAssetLiveConfig:
    """Load an armed config without contacting the venue."""
    return load_multi_asset_live_config(
        source,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )


def _provider(
    config: MultiAssetLiveConfig,
    strategy_id: str,
) -> StrategyProviderConfig:
    """Return one exact strategy provider from a profile."""
    return next(row for row in config.providers if row.strategy_id == strategy_id)


def _restore_v63(
    candidate: MultiAssetLiveConfig,
    baseline: MultiAssetLiveConfig,
    gold: AssetLiveConfig,
    old_provider: StrategyProviderConfig,
) -> MultiAssetLiveConfig:
    """Normalize the authorized V64 deltas back to the V63 identity."""
    assets = tuple(
        replace(asset, parent_profile_id=baseline.profile_id)
        for asset in candidate.assets
    )
    providers = tuple(
        old_provider if row.strategy_id == _HIP3 else row for row in candidate.providers
    )
    return replace(
        candidate,
        profile_id=baseline.profile_id,
        source_path=baseline.source_path,
        assets=(*assets, gold),
        providers=providers,
        transition_approval=baseline.transition_approval,
    )
