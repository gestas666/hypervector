"""Configuration identity tests for explicit profile-change approvals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import pytest

from hypervector.live import multi_asset_live_config
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

# Profile without a transition approval.
_COMPLETE_PORTFOLIO = Path("tests/fixtures/profiles/complete_portfolio.toml")
_CHAIN = Path("tests/fixtures/cohort_chain")
_PROFILE_A = _CHAIN / "profile_a.toml"
_PROFILE_B = _CHAIN / "profile_b.toml"
_ROLLBACK_B_TO_A = _CHAIN / "rollback_b_to_a.toml"


def test_existing_profile_preserves_identity_without_transition_approval(
    tmp_path: Path,
) -> None:
    """Adding the optional boundary must not drift an incumbent fingerprint."""
    config = load_multi_asset_live_config(_COMPLETE_PORTFOLIO, mode="observe")
    assert config.transition_approval is None

    copy = tmp_path / _COMPLETE_PORTFOLIO.name
    copy.write_bytes(_COMPLETE_PORTFOLIO.read_bytes())
    reloaded = load_multi_asset_live_config(copy, mode="observe")
    assert reloaded.profile_fingerprint == config.profile_fingerprint

    hashed = _hashed_profile_values(config)
    assert "profile_id" in hashed
    assert "transition_approval" not in hashed
    approved = replace(config, transition_approval=Path("approval.json"))
    assert replace(approved, transition_approval=None).profile_fingerprint == (
        config.profile_fingerprint
    )


def test_transition_approval_path_is_part_of_candidate_identity(
    tmp_path: Path,
) -> None:
    """A candidate binds the exact approval source path into its fingerprint."""
    control = load_multi_asset_live_config(_COMPLETE_PORTFOLIO, mode="observe")
    raw = _COMPLETE_PORTFOLIO.read_text(encoding="utf-8")
    assert raw.count("lookback_days = 14\n") == 1
    candidate_path = tmp_path / "candidate.toml"
    candidate_path.write_text(
        raw.replace(
            "lookback_days = 14\n",
            'lookback_days = 14\ntransition_approval = "approval.json"\n',
            1,
        ),
        encoding="utf-8",
    )

    candidate = load_multi_asset_live_config(candidate_path, mode="observe")
    renamed = replace(candidate, transition_approval=Path("other-approval.json"))

    assert candidate.transition_approval == Path("approval.json")
    assert candidate.profile_fingerprint != control.profile_fingerprint
    assert renamed.profile_fingerprint not in {
        control.profile_fingerprint,
        candidate.profile_fingerprint,
    }


def test_rollback_twin_differs_from_profile_a_only_by_approval_identity() -> None:
    """The rollback profile is profile A bytes with only its approval path changed."""
    profile_a = load_multi_asset_live_config(_PROFILE_A, mode="observe")
    rollback = load_multi_asset_live_config(_ROLLBACK_B_TO_A, mode="observe")

    assert _setting_lines(_PROFILE_A, "transition_approval") == _setting_lines(
        _ROLLBACK_B_TO_A, "transition_approval"
    )
    assert rollback.profile_id == profile_a.profile_id
    assert rollback.transition_approval != profile_a.transition_approval
    assert rollback.profile_fingerprint != profile_a.profile_fingerprint


def test_chain_profiles_match_their_hash_bound_approvals() -> None:
    """Each chain profile reproduces the fingerprint its approval binds."""
    profile_a = load_multi_asset_live_config(_PROFILE_A, mode="observe")
    profile_b = load_multi_asset_live_config(_PROFILE_B, mode="observe")
    rollback = load_multi_asset_live_config(_ROLLBACK_B_TO_A, mode="observe")
    forward = _approval(profile_b.transition_approval)
    backward = _approval(rollback.transition_approval)

    assert forward["previous_profile"] == _identity(profile_a)
    assert forward["candidate_profile"] == _identity(profile_b)
    assert backward["previous_profile"] == _identity(profile_b)
    assert backward["candidate_profile"] == _identity(rollback)
    assert forward["rollback"]["profile_fingerprint"] == profile_a.profile_fingerprint
    assert backward["rollback"]["profile_fingerprint"] == profile_b.profile_fingerprint


def _hashed_profile_values(config: MultiAssetLiveConfig) -> Mapping[str, object]:
    """Return the identity mapping hashed into one profile fingerprint."""
    original = multi_asset_live_config.stable_fingerprint
    seen: list[Mapping[str, object]] = []

    def spy(values: Mapping[str, object]) -> str:
        seen.append(values)
        return original(values)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(multi_asset_live_config, "stable_fingerprint", spy)
        fingerprint = config.profile_fingerprint
    assert fingerprint == original(seen[-1])
    return seen[-1]


def _setting_lines(path: Path, excluded_key: str) -> list[str]:
    """Return profile setting lines without comments or one excluded key."""
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        and not line.lstrip().startswith("#")
        and not line.startswith(f"{excluded_key} =")
    ]


def _approval(path: Path | None) -> dict[str, Any]:
    assert path is not None
    document = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _identity(config: MultiAssetLiveConfig) -> dict[str, str]:
    return {
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
    }
