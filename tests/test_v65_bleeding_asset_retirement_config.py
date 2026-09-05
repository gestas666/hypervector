"""Acceptance contract for the evidence-driven V65 bleeding stop."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hypervector.live.cohort_profile_change_approval import (
    validate_profile_change_approval,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

_V64 = Path(
    "configs/multi_asset_growth_first_5000_eight_asset_gold_removed_candidate_v64.toml"
)
_V65 = Path(
    "configs/multi_asset_growth_first_5000_five_asset_bleeding_stopped_candidate_v65.toml"
)
_PROFILE = "multi_asset_growth_first_5000_five_asset_bleeding_stopped_candidate_v65"
_APPROVAL = Path(
    "docs/live-approvals/"
    "v64-to-v65-bleeding-assets-retired-approved-for-live-transition-20260901-v1.json"
)
_REMOVED_SYMBOLS = {"ETH", "xyz:SP500", "xyz:SPCX"}
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_REMOVED_PROVIDERS = {
    "eth_breakout_precompression_pullback_bidirectional_v1",
    "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
    "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1",
}


def test_v65_terminally_removes_only_the_three_bleeding_assets() -> None:
    """V65 must preserve every retained V64 asset and execution contract."""
    baseline = _load(_V64)
    candidate = _load(_V65)
    expected_assets = tuple(
        replace(asset, parent_profile_id=candidate.profile_id)
        for asset in baseline.assets
        if asset.symbol not in _REMOVED_SYMBOLS
    )

    assert candidate.profile_id == _PROFILE
    assert candidate.transition_approval == _APPROVAL
    assert candidate.assets == expected_assets
    assert candidate.symbols == (
        "BTC",
        "SOL",
        "HYPE",
        "xyz:SNDK",
        "xyz:BRENTOIL",
    )
    assert candidate.maximum_positions == baseline.maximum_positions


def test_v65_preserves_retained_routes_and_removes_every_retired_scope() -> None:
    """No ETH or index direction may remain reachable through a shared provider."""
    baseline = _load(_V64)
    candidate = _load(_V65)
    providers = {row.strategy_id: row for row in candidate.providers}
    baseline_providers = {row.strategy_id: row for row in baseline.providers}

    assert _REMOVED_PROVIDERS.isdisjoint(providers)
    assert providers[_HULK] == replace(
        baseline_providers[_HULK],
        symbols=("BTC", "SOL"),
        execution_symbols=("BTC", "SOL"),
    )
    for strategy_id, provider in providers.items():
        assert _REMOVED_SYMBOLS.isdisjoint(provider.execution_symbols)
        if strategy_id != _HULK:
            assert provider == baseline_providers[strategy_id]
    assert len(candidate.executable_provider_directions) == 13


def test_v65_approval_records_ten_terminal_retirements() -> None:
    """Every removed symbol-side scope must be explicit and replacement-free."""
    baseline = _load(_V64)
    candidate = _load(_V65)

    evidence = validate_profile_change_approval(
        baseline,
        candidate,
        candidate.transition_approval,
    )

    assert evidence["state"] == "approved_profile_change"
    assert len(evidence["retired_execution_scopes"]) == 10
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
