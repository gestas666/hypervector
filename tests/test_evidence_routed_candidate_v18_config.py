"""Contract tests for the inactive post-v14 evidence-routed candidate."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_live_config_parsing import (
    MultiAssetLiveConfigError,
)

_V14 = Path(
    "configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml"
)
_V18 = Path("configs/multi_asset_bidirectional_evidence_routed_candidate_v18.toml")
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_BREAKOUT = "hype_breakout_onset_bidirectional_v1"
_ETH_PULLBACK = "eth_breakout_precompression_pullback_bidirectional_v1"


def test_v18_changes_only_post_v14_execution_routing_and_identity() -> None:
    """Each executable coin has one evidence-selected provider."""
    assert _V18.is_file(), "the inactive v18 candidate is missing"
    prior = load_multi_asset_live_config(_V14, mode="observe")
    candidate = load_multi_asset_live_config(_V18, mode="observe")
    before = {provider.strategy_id: provider for provider in prior.providers}
    after = {provider.strategy_id: provider for provider in candidate.providers}

    assert candidate.profile_id == (
        "multi_asset_bidirectional_evidence_routed_candidate_v18"
    )
    assert candidate.maximum_positions == prior.maximum_positions == 4
    assert candidate.maximum_positions == len(candidate.assets)
    assert all(asset.max_positions_per_symbol == 1 for asset in candidate.assets)
    assert candidate.assets == tuple(
        replace(asset, parent_profile_id=candidate.profile_id) for asset in prior.assets
    )
    assert candidate.executable_provider_symbols == {
        (_HULK, "BTC"),
        (_ETH_PULLBACK, "ETH"),
        (_BREAKOUT, "HYPE"),
    }
    assert after[_BREAKOUT] == replace(before[_BREAKOUT], execution_symbols=("HYPE",))
    assert after[_ETH_PULLBACK] == replace(
        before[_ETH_PULLBACK], execution_symbols=("ETH",)
    )
    assert all(
        after[strategy_id] == provider
        for strategy_id, provider in before.items()
        if strategy_id not in {_BREAKOUT, _ETH_PULLBACK}
    )


@pytest.mark.integration
def test_v18_preserves_bidirectional_risk_and_builds_collectors() -> None:
    """Routing does not change risk, sides, or collector availability."""
    config = load_multi_asset_live_config(_V18, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}
    assets = {asset.symbol: asset for asset in config.assets}
    eth = providers[_ETH_PULLBACK]

    assert all(
        provider.sides == frozenset({"long", "short"})
        for provider in providers.values()
    )
    assert all(asset.leverage == 5.0 for asset in assets.values())
    assert assets["BTC"].max_notional_usd == 25.0
    assert assets["ETH"].max_notional_usd == 25.0
    assert assets["SOL"].max_notional_usd == 75.0
    assert assets["HYPE"].max_notional_usd == 75.0
    assert eth.execution.stop_bps == 60.0
    assert eth.execution.target_policy == "none"
    assert eth.execution.maximum_hold_seconds == 43_200
    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: None,
        backtest_lab_root=Path("../backtest-lab/backtest_lab").resolve(),
    )
    assert poller is not None


def test_v18_remains_fail_closed_without_live_authority() -> None:
    """The candidate cannot weaken the explicit two-flag live contract."""
    config = load_multi_asset_live_config(_V18, mode="live")

    with pytest.raises(MultiAssetLiveConfigError, match="--enabled"):
        config.require_live_start(credentials_present=True)
