"""Configuration identity tests for explicit profile-change approvals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

# Kept profile without a transition approval; its fingerprint was recorded before
# the optional [runtime] transition_approval boundary existed.
_V25 = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")
_V95 = Path("configs/multi_asset_growth_first_5000_review_fixes_v95.toml")
_V94 = Path("configs/multi_asset_growth_first_5000_review_actions_v94.toml")
_V95_TO_V94_ROLLBACK = Path("configs/v95-to-v94-rollback-20260927-v1.toml")


def test_existing_profile_preserves_identity_without_transition_approval() -> None:
    """Adding the optional boundary must not drift an incumbent fingerprint."""
    config = load_multi_asset_live_config(_V25, mode="observe")

    assert config.transition_approval is None
    assert config.profile_fingerprint == (
        "ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc"
    )


def test_transition_approval_path_is_part_of_candidate_identity(
    tmp_path: Path,
) -> None:
    """A candidate binds the exact approval source path into its fingerprint."""
    control = load_multi_asset_live_config(_V25, mode="observe")
    raw = _V25.read_text(encoding="utf-8")
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

    assert candidate.transition_approval == Path("approval.json")
    assert candidate.profile_fingerprint != control.profile_fingerprint


def test_rollback_twin_differs_from_v94_only_by_approval_identity() -> None:
    """The kept rollback profile is V94 bytes with only its approval path changed."""
    v94 = load_multi_asset_live_config(_V94, mode="observe")
    rollback = load_multi_asset_live_config(_V95_TO_V94_ROLLBACK, mode="observe")

    assert _setting_lines(_V94, "transition_approval") == _setting_lines(
        _V95_TO_V94_ROLLBACK, "transition_approval"
    )
    assert rollback.profile_id == v94.profile_id
    assert rollback.transition_approval != v94.transition_approval
    assert rollback.profile_fingerprint != v94.profile_fingerprint


def test_live_profiles_match_their_hash_bound_approvals() -> None:
    """Each kept live profile reproduces the fingerprint its approval binds."""
    v94 = load_multi_asset_live_config(_V94, mode="observe")
    v95 = load_multi_asset_live_config(_V95, mode="observe")
    rollback = load_multi_asset_live_config(_V95_TO_V94_ROLLBACK, mode="observe")
    forward = _approval(v95.transition_approval)
    backward = _approval(rollback.transition_approval)

    assert forward["previous_profile"] == _identity(v94)
    assert forward["candidate_profile"] == _identity(v95)
    assert backward["previous_profile"] == _identity(v95)
    assert backward["candidate_profile"] == _identity(rollback)
    assert forward["rollback"]["profile_fingerprint"] == v94.profile_fingerprint
    assert backward["rollback"]["profile_fingerprint"] == v95.profile_fingerprint


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
