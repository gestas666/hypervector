"""Acceptance contract for the evidence-driven V66 BRENTOIL retirement."""

from __future__ import annotations

import pytest

from dataclasses import replace
from pathlib import Path

from hypervector.live.cohort_profile_change_approval import (
    validate_profile_change_approval,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

_V65 = Path(
    "configs/multi_asset_growth_first_5000_five_asset_bleeding_stopped_candidate_v65.toml"
)
_V66 = Path(
    "configs/multi_asset_growth_first_5000_four_asset_brentoil_retired_candidate_v66.toml"
)
_PROFILE = "multi_asset_growth_first_5000_four_asset_brentoil_retired_candidate_v66"
_APPROVAL = Path(
    "docs/live-approvals/"
    "v65-to-v66-brentoil-retired-approved-for-live-transition-20260901-v1.json"
)
_BRENTOIL = "xyz:BRENTOIL"
_HIP3 = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"


def test_v66_removes_only_brentoil_and_preserves_retained_contracts() -> None:
    """V66 must retain every non-BRENTOIL V65 asset and route contract."""
    baseline = _load(_V65)
    candidate = _load(_V66)
    expected_assets = tuple(
        replace(asset, parent_profile_id=candidate.profile_id)
        for asset in baseline.assets
        if asset.symbol != _BRENTOIL
    )
    baseline_providers = {row.strategy_id: row for row in baseline.providers}
    candidate_providers = {row.strategy_id: row for row in candidate.providers}

    assert candidate.profile_id == _PROFILE
    assert candidate.transition_approval == _APPROVAL
    assert candidate.assets == expected_assets
    assert candidate.symbols == ("BTC", "SOL", "HYPE", "xyz:SNDK")
    assert candidate.maximum_positions == baseline.maximum_positions
    assert candidate_providers[_HIP3] == replace(
        baseline_providers[_HIP3],
        symbols=("xyz:SNDK",),
        execution_symbols=("xyz:SNDK",),
    )
    for strategy_id, provider in candidate_providers.items():
        if strategy_id != _HIP3:
            assert provider == baseline_providers[strategy_id]


def test_v66_has_no_reachable_brentoil_execution_scope() -> None:
    """Neither BRENTOIL direction may remain reachable through shared routing."""
    candidate = _load(_V66)

    assert _BRENTOIL not in candidate.symbols
    assert len(candidate.executable_provider_directions) == 11
    assert all(
        symbol != _BRENTOIL for _, symbol, _ in candidate.executable_provider_directions
    )


@pytest.mark.evidence
def test_v66_approval_records_two_terminal_retirements() -> None:
    """The exact V65-to-V66 approval must retire both Brent directions."""
    baseline = _load(_V65)
    candidate = _load(_V66)

    evidence = validate_profile_change_approval(
        baseline,
        candidate,
        candidate.transition_approval,
    )

    assert evidence["state"] == "approved_profile_change"
    assert evidence["retired_execution_scopes"] == [
        f"{_HIP3}|{_BRENTOIL}|long",
        f"{_HIP3}|{_BRENTOIL}|short",
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
