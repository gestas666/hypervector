"""Contract tests for the separate fixed-eight-hour HYPE exit candidate."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_BASE = Path("configs/multi_asset_bidirectional_range_retired_candidate.toml")
_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_range_retired_hype_fixed8_candidate.toml"
)
_HYPE = "hype_breakout_onset_bidirectional_v1"
_RANGE = "range_onset_bidirectional_v1"


def test_fixed8_candidate_changes_only_canonical_hype_exit_contract() -> None:
    """The new profile isolates its one evidence-backed lifecycle change."""
    base = load_multi_asset_live_config(_BASE, mode="observe")
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    base_providers = {row.strategy_id: row for row in base.providers}
    candidate_providers = {row.strategy_id: row for row in candidate.providers}

    assert (
        candidate.profile_id == "multi_asset_bidirectional_range_retired_hype_fixed8_v4"
    )
    assert (
        candidate.executable_provider_directions == base.executable_provider_directions
    )
    assert candidate.maximum_positions == base.maximum_positions
    assert candidate_providers.keys() == base_providers.keys()
    assert candidate_providers[_RANGE].execution_symbols == ()

    for asset, base_asset in zip(candidate.assets, base.assets, strict=True):
        assert replace(asset, parent_profile_id=base.profile_id) == base_asset
    for strategy_id, provider in candidate_providers.items():
        if strategy_id != _HYPE:
            assert provider == base_providers[strategy_id]

    hype = candidate_providers[_HYPE]
    base_hype = base_providers[_HYPE]
    assert hype.sides == frozenset({"long", "short"})
    assert hype.execution_symbols == ("HYPE",)
    assert hype.execution.maximum_hold_seconds == 28_800
    assert hype.execution.maximum_hold_policy == "fixed"
    assert hype.execution.hard_maximum_hold_seconds is None
    assert (
        replace(
            hype.execution,
            maximum_hold_policy=base_hype.execution.maximum_hold_policy,
            hard_maximum_hold_seconds=base_hype.execution.hard_maximum_hold_seconds,
        )
        == base_hype.execution
    )
