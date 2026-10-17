"""Acceptance contract for the explicitly approved V62 live update."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live.cohort_profile_change_approval import (
    validate_profile_change_approval,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
    validate_multi_asset_live_config,
)
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError

_V61 = Path(
    "configs/"
    "multi_asset_growth_first_5000_eight_asset_sndk_exit_preserved_candidate_v61.toml"
)
_V62 = Path(
    "configs/multi_asset_growth_first_5000_eight_asset_hype_a60_candidate_v62.toml"
)
_APPROVAL = Path(
    "docs/live-approvals/"
    "v61-to-v62-hype-a60-approved-for-live-transition-20260829-v1.json"
)
_PROFILE = "multi_asset_growth_first_5000_eight_asset_hype_a60_candidate_v62"
_HYPE = "hype_breakout_compression_alignment_bidirectional_v2"


def test_v62_changes_only_hype_profit_lock_and_transition_metadata() -> None:
    """V62 must preserve V61 except for the exact A60 exit and approval source."""
    baseline = _load(_V61)
    candidate = _load(_V62)
    old_hype = _provider(baseline, _HYPE)
    new_hype = _provider(candidate, _HYPE)

    assert candidate.profile_id == _PROFILE
    assert candidate.transition_approval == _APPROVAL
    assert new_hype == replace(
        old_hype,
        execution=replace(
            old_hype.execution,
            profit_lock_policy="completed_bar_trailing",
            profit_lock_activation_bps=60.0,
            profit_lock_floor_bps=15.0,
            profit_lock_giveback_bps=30.0,
        ),
    )
    assert _normalized(candidate, baseline, new_hype, old_hype) == baseline


def test_v62_retires_no_execution_scope() -> None:
    """The exit update cannot masquerade as a strategy retirement."""
    baseline = _load(_V61)
    candidate = _load(_V62)

    assert candidate.executable_provider_directions == (
        baseline.executable_provider_directions
    )


def test_v62_hype_profit_lock_rejects_parameter_drift() -> None:
    """The provider validator accepts only the exact approved A60 policy."""
    candidate = _load(_V62)
    hype = _provider(candidate, _HYPE)
    drifted = replace(
        hype,
        execution=replace(hype.execution, profit_lock_giveback_bps=31.0),
    )
    providers = tuple(
        drifted if provider == hype else provider for provider in candidate.providers
    )

    with pytest.raises(MultiAssetLiveConfigError, match="exact fresh"):
        validate_multi_asset_live_config(replace(candidate, providers=providers))


@pytest.mark.evidence
def test_v62_exact_operator_approval_authorizes_the_profile_change() -> None:
    """The approved transition binds exact profiles, evidence, and rollback."""
    baseline = _load(_V61)
    candidate = _load(_V62)

    evidence = validate_profile_change_approval(
        baseline,
        candidate,
        candidate.transition_approval,
    )

    assert evidence["state"] == "approved_profile_change"
    assert evidence["approval_status"] == "approved_for_live_transition"
    assert evidence["retired_execution_scopes"] == []
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
    """Return one exact provider from a profile fixture."""
    return next(row for row in config.providers if row.strategy_id == strategy_id)


def _normalized(
    candidate: MultiAssetLiveConfig,
    baseline: MultiAssetLiveConfig,
    new_hype: StrategyProviderConfig,
    old_hype: StrategyProviderConfig,
) -> MultiAssetLiveConfig:
    """Normalize the authorized V62 deltas back to the V61 identity."""
    providers = tuple(
        old_hype if provider == new_hype else provider
        for provider in candidate.providers
    )
    return replace(
        candidate,
        profile_id=baseline.profile_id,
        source_path=baseline.source_path,
        assets=tuple(
            replace(asset, parent_profile_id=baseline.profile_id)
            for asset in candidate.assets
        ),
        providers=providers,
        transition_approval=None,
    )
