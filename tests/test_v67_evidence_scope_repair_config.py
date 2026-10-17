"""Acceptance contract for the V67 evidence-scope repair."""

from __future__ import annotations

import pytest

from dataclasses import replace
from pathlib import Path

from hypervector.live.cohort_profile_change_approval import (
    validate_profile_change_approval,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
)

_V66 = Path(
    "configs/multi_asset_growth_first_5000_four_asset_"
    "brentoil_retired_candidate_v66.toml"
)
_V67 = Path(
    "configs/multi_asset_growth_first_5000_three_asset_"
    "evidence_scope_repaired_candidate_v67.toml"
)
_PROFILE = (
    "multi_asset_growth_first_5000_three_asset_evidence_scope_repaired_candidate_v67"
)
_APPROVAL = Path(
    "docs/live-approvals/"
    "v66-to-v67-evidence-scope-repair-approved-for-live-transition-"
    "20260901-v1.json"
)
_REJECTED_HULK = "hulk_expansion_bidirectional_tuned_v2"
_SNDK_PRESSURE = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"


def test_v67_removes_rejected_hulk_and_orphaned_sol() -> None:
    """The rejected bidirectional provider and its sole SOL asset must be absent."""
    baseline = _load(_V66)
    candidate = _load(_V67)

    assert candidate.profile_id == _PROFILE
    assert candidate.maximum_positions == 3
    assert candidate.symbols == ("BTC", "HYPE", "xyz:SNDK")
    assert candidate.assets == tuple(
        replace(asset, parent_profile_id=candidate.profile_id)
        for asset in baseline.assets
        if asset.symbol != "SOL"
    )
    assert _REJECTED_HULK not in {
        provider.strategy_id for provider in candidate.providers
    }
    assert all(
        symbol != "SOL" for _, symbol, _ in candidate.executable_provider_directions
    )


def test_v67_restores_sndk_short_only_execution_authority() -> None:
    """SNDK long stays observable but cannot route after the V64 regression."""
    candidate = _load(_V67)
    provider = _provider(candidate, _SNDK_PRESSURE)

    assert provider.sides == frozenset({"long", "short"})
    assert provider.execution_side_overrides == (("xyz:SNDK", frozenset({"short"})),)
    assert (_SNDK_PRESSURE, "xyz:SNDK", "long") not in (
        candidate.executable_provider_directions
    )
    assert (_SNDK_PRESSURE, "xyz:SNDK", "short") in (
        candidate.executable_provider_directions
    )


def test_v67_preserves_the_five_retained_provider_contracts() -> None:
    """No retained entry, exit, priority, cadence, or sizing contract may drift."""
    baseline = _load(_V66)
    candidate = _load(_V67)
    expected = tuple(
        provider
        for provider in baseline.providers
        if provider.strategy_id != _REJECTED_HULK
    )
    actual = tuple(
        replace(
            provider,
            execution_side_overrides=(),
        )
        if provider.strategy_id == _SNDK_PRESSURE
        else provider
        for provider in candidate.providers
    )

    assert actual == expected
    assert len(candidate.providers) == 5
    assert candidate.executable_provider_directions == frozenset(
        {
            ("hulk_expansion_short_robust_v3", "BTC", "short"),
            ("hulk_expansion_short_tuned_v2", "BTC", "short"),
            ("liquidity_sweep_long_1h_stop60_target60_v2", "BTC", "long"),
            (
                "hype_breakout_compression_alignment_bidirectional_v2",
                "HYPE",
                "long",
            ),
            (
                "hype_breakout_compression_alignment_bidirectional_v2",
                "HYPE",
                "short",
            ),
            (_SNDK_PRESSURE, "xyz:SNDK", "short"),
        }
    )


@pytest.mark.evidence
def test_v67_approval_records_every_removed_execution_scope() -> None:
    """The transition approval must exactly bind all five removed directions."""
    baseline = _load(_V66)
    candidate = _load(_V67)

    evidence = validate_profile_change_approval(
        baseline,
        candidate,
        candidate.transition_approval,
    )

    assert candidate.transition_approval == _APPROVAL
    assert evidence["state"] == "approved_profile_change"
    assert evidence["retired_execution_scopes"] == [
        f"{_SNDK_PRESSURE}|xyz:SNDK|long",
        f"{_REJECTED_HULK}|BTC|long",
        f"{_REJECTED_HULK}|BTC|short",
        f"{_REJECTED_HULK}|SOL|long",
        f"{_REJECTED_HULK}|SOL|short",
    ]
    assert evidence["replacement_execution_scopes"] == []
    assert evidence["execution_authority"] == "none"


def _load(path: Path) -> MultiAssetLiveConfig:
    """Load one live-authorized profile without contacting the venue."""
    return load_multi_asset_live_config(
        path,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )


def _provider(
    config: MultiAssetLiveConfig,
    strategy_id: str,
) -> StrategyProviderConfig:
    """Return the single provider with the requested strategy identity."""
    return next(row for row in config.providers if row.strategy_id == strategy_id)
