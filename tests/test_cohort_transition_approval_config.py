"""Configuration identity tests for explicit profile-change approvals."""

from __future__ import annotations

from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_V61 = Path(
    "configs/"
    "multi_asset_growth_first_5000_eight_asset_sndk_exit_preserved_candidate_v61.toml"
)


def test_existing_profile_preserves_identity_without_transition_approval() -> None:
    """Adding the optional boundary must not drift an incumbent fingerprint."""
    config = load_multi_asset_live_config(_V61, mode="observe")

    assert config.transition_approval is None
    assert config.profile_fingerprint == (
        "3ca27a84d7ccd9c8a3fb8ba6a41990048ef5ec6440c9e51df6c30bba72917267"
    )


def test_transition_approval_path_is_part_of_candidate_identity(
    tmp_path: Path,
) -> None:
    """A candidate binds the exact approval source path into its fingerprint."""
    control = load_multi_asset_live_config(_V61, mode="observe")
    raw = _V61.read_text(encoding="utf-8")
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
