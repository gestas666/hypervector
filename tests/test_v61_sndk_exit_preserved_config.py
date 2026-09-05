"""Acceptance contract for the V61 SNDK exit-preserving successor."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

_V60 = Path(
    "configs/multi_asset_growth_first_5000_eight_asset_"
    "btc_hulk_smart_exit_candidate_v60.toml"
)
_V61 = Path(
    "configs/multi_asset_growth_first_5000_eight_asset_"
    "sndk_exit_preserved_candidate_v61.toml"
)
_PROFILE = "multi_asset_growth_first_5000_eight_asset_sndk_exit_preserved_candidate_v61"


def test_v61_preserves_every_v60_execution_contract() -> None:
    """The restart changes identity only and introduces no strategy drift."""
    baseline = _load(_V60)
    candidate = _load(_V61)

    assert candidate.profile_id == _PROFILE
    assert candidate.assets == tuple(
        replace(asset, parent_profile_id=candidate.profile_id)
        for asset in baseline.assets
    )
    assert candidate.providers == baseline.providers
    assert candidate.cohort_ledger == baseline.cohort_ledger
    assert candidate.stop_file == baseline.stop_file
    assert candidate.poll_seconds == baseline.poll_seconds
    assert candidate.lookback_days == baseline.lookback_days
    assert candidate.maximum_positions == baseline.maximum_positions


def test_v61_keeps_all_eight_assets_and_sndk_short_execution() -> None:
    """SNDK remains live short-only with its validated unchanged exit contract."""
    candidate = _load(_V61)

    assert len(candidate.assets) == 8
    assert "xyz:SNDK" in candidate.symbols
    provider = next(
        row for row in candidate.providers if "xyz:SNDK" in row.execution_symbols
    )
    assert provider.execution_symbols == ("xyz:SNDK", "xyz:BRENTOIL")
    assert provider.execution_side_overrides == (("xyz:SNDK", frozenset({"short"})),)
    assert provider.execution.target_policy == "none"
    assert provider.execution.stop_bps == 80.0
    assert provider.execution.maximum_hold_seconds == 86_400
    assert provider.execution.profit_lock_policy == "none"


def _load(path: Path) -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(
        path,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
