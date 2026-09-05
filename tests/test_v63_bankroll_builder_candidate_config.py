"""Acceptance contract for the proposed V63 bankroll builder live update."""

from __future__ import annotations

from pathlib import Path

from hypervector.live.cohort_profile_change_approval import (
    validate_profile_change_approval,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

_V62 = Path(
    "configs/multi_asset_growth_first_5000_eight_asset_hype_a60_candidate_v62.toml"
)
_V63 = Path(
    "configs/"
    "multi_asset_growth_first_5000_nine_asset_bankroll_builder_candidate_v63.toml"
)
_APPROVAL = Path(
    "docs/live-approvals/"
    "v62-to-v63-bankroll-builder-approved-for-live-transition-20260831-v1.json"
)
_PROFILE = "multi_asset_growth_first_5000_nine_asset_bankroll_builder_candidate_v63"


def test_v63_config_loads_and_validates_successfully() -> None:
    """V63 must load, validate, and contain all 9 assets with 25 executable directions."""
    candidate = _load(_V63)
    assert candidate.profile_id == _PROFILE
    assert len(candidate.symbols) == 9
    assert set(candidate.symbols) == {
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SP500",
        "xyz:SPCX",
        "xyz:SNDK",
        "xyz:BRENTOIL",
        "xyz:GOLD",
    }
    assert len(candidate.executable_provider_directions) == 25
    assert candidate.transition_approval == _APPROVAL


def test_v63_retires_no_execution_scope_from_v62() -> None:
    """V63 is a strict superset of V62, preserving all existing routes and unblocking high-alpha scopes."""
    baseline = _load(_V62)
    candidate = _load(_V63)

    assert baseline.executable_provider_directions.issubset(
        candidate.executable_provider_directions
    )


def test_v63_transition_approval_is_valid() -> None:
    """The transition approval document binds V62 to V63 with valid cryptographic hashes."""
    baseline = _load(_V62)
    candidate = _load(_V63)

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
