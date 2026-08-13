"""Contract tests for the inactive all-asset breakout v14 live profile."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_live_config_parsing import (
    MultiAssetLiveConfigError,
)

_V11 = Path(
    "configs/multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11.toml"
)
_V14 = Path(
    "configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml"
)
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_BREAKOUT = "hype_breakout_onset_bidirectional_v1"
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")


def test_v14_changes_only_canonical_breakout_execution_scope() -> None:
    """All four coins may execute the unchanged v1 breakout contract."""
    assert _V14.is_file(), "the approved all-asset breakout profile is missing"
    prior = load_multi_asset_live_config(_V11, mode="observe")
    candidate = load_multi_asset_live_config(_V14, mode="observe")
    before = {provider.strategy_id: provider for provider in prior.providers}
    after = {provider.strategy_id: provider for provider in candidate.providers}

    assert candidate.profile_id == (
        "multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14"
    )
    assert candidate.maximum_positions == prior.maximum_positions == 4
    assert candidate.assets == tuple(
        replace(asset, parent_profile_id=candidate.profile_id) for asset in prior.assets
    )
    assert candidate.executable_provider_symbols == {
        (_HULK, "BTC"),
        *((_BREAKOUT, symbol) for symbol in _SYMBOLS),
    }
    assert after[_BREAKOUT] == replace(before[_BREAKOUT], execution_symbols=_SYMBOLS)
    assert all(
        after[strategy_id] == provider
        for strategy_id, provider in before.items()
        if strategy_id != _BREAKOUT
    )

    assets = {asset.symbol: asset for asset in candidate.assets}
    assert assets["BTC"].max_notional_usd == 25.0
    assert assets["ETH"].max_notional_usd == 25.0
    assert assets["SOL"].max_notional_usd == 75.0
    assert assets["HYPE"].max_notional_usd == 75.0
    assert all(asset.leverage == 5.0 for asset in assets.values())
    assert all(asset.sides == frozenset({"long", "short"}) for asset in assets.values())


def test_v14_remains_fail_closed_without_explicit_live_authority() -> None:
    """The broader route cannot weaken the two-flag live-start contract."""
    assert _V14.is_file(), "the approved all-asset breakout profile is missing"
    config = load_multi_asset_live_config(_V14, mode="live")

    with pytest.raises(MultiAssetLiveConfigError, match="--enabled"):
        config.require_live_start(credentials_present=True)
