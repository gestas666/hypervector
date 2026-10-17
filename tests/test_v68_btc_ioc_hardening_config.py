"""Acceptance contract for the V68 BTC IOC hardening successor."""

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
from hypervector.live.multi_asset_cohort_payloads import asset_config_payload
from hypervector.research.cohort_configuration_generation import (
    configuration_generation_evidence,
    load_configuration_expectation,
)

_V67 = Path(
    "configs/multi_asset_growth_first_5000_three_asset_"
    "evidence_scope_repaired_candidate_v67.toml"
)
_V68 = Path(
    "configs/multi_asset_growth_first_5000_three_asset_"
    "btc_ioc_hardened_candidate_v68.toml"
)
_PROFILE = "multi_asset_growth_first_5000_three_asset_btc_ioc_hardened_candidate_v68"
_BTC_ENTRY_AND_CLOSE_IOC_CAP = 0.002
_APPROVAL = Path(
    "docs/live-approvals/"
    "v67-to-v68-btc-ioc-hardening-approved-for-live-transition-20260901-v1.json"
)


def test_v68_changes_only_identity_approval_and_btc_ioc_cap() -> None:
    """V68 must preserve V67 while bounding BTC IOC execution to 20 bps."""
    assert _V68.is_file(), "V68 BTC IOC hardening profile is missing"
    baseline = _load(_V67)
    candidate = _load(_V68)

    assert candidate.profile_id == _PROFILE
    assert candidate.assets == tuple(
        replace(
            asset,
            parent_profile_id=candidate.profile_id,
            market_slippage_cap_fraction=(
                _BTC_ENTRY_AND_CLOSE_IOC_CAP
                if asset.symbol == "BTC"
                else asset.market_slippage_cap_fraction
            ),
        )
        for asset in baseline.assets
    )
    normalized = replace(
        candidate,
        profile_id=baseline.profile_id,
        source_path=baseline.source_path,
        transition_approval=baseline.transition_approval,
        assets=baseline.assets,
    )
    assert normalized == baseline


@pytest.mark.evidence
def test_v68_approval_binds_the_ioc_only_profile_change() -> None:
    """The operator approval must authenticate V67, V68, evidence, and rollback."""
    assert _APPROVAL.is_file(), "V68 BTC IOC hardening approval is missing"
    baseline = _load(_V67)
    candidate = _load(_V68)

    evidence = validate_profile_change_approval(
        baseline,
        candidate,
        candidate.transition_approval,
    )

    assert candidate.transition_approval == _APPROVAL
    assert evidence["state"] == "approved_profile_change"
    assert evidence["retired_execution_scopes"] == []
    assert evidence["replacement_execution_scopes"] == []
    assert evidence["execution_authority"] == "none"


def test_v68_projects_ioc_caps_into_backend_and_restart_telemetry() -> None:
    """The TUI inputs must expose the exact effective and pending IOC bounds."""
    candidate = _load(_V68)
    effective = {
        asset.symbol: asset_config_payload(asset) for asset in candidate.assets
    }
    pending = configuration_generation_evidence(
        candidate.profile_fingerprint,
        load_configuration_expectation(_V68),
        {
            asset.symbol: {
                "final_state": "FLAT",
                "position_size_signed": 0.0,
                "open_order_ids": [],
            }
            for asset in candidate.assets
        },
    )

    assert effective["BTC"]["market_slippage_cap_fraction"] == 0.002
    assert effective["HYPE"]["market_slippage_cap_fraction"] == 0.01
    assert effective["xyz:SNDK"]["market_slippage_cap_fraction"] == 0.01
    assert pending["current_asset_market_slippage_caps"] == {
        "BTC": 0.002,
        "HYPE": 0.01,
        "xyz:SNDK": 0.01,
    }


def _load(path: Path) -> MultiAssetLiveConfig:
    """Load one profile without constructing a venue client."""
    return load_multi_asset_live_config(
        path,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
