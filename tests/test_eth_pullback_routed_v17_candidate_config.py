"""Contract tests for the inactive v14-plus-ETH-pullback candidate."""

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
_V17 = Path(
    "configs/multi_asset_bidirectional_hype75_eth_pullback_routed_candidate_v17.toml"
)
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_BREAKOUT = "hype_breakout_onset_bidirectional_v1"
_ETH_PULLBACK = "eth_breakout_precompression_pullback_bidirectional_v1"


def test_v17_replaces_only_eth_generic_breakout_execution() -> None:
    """ETH uses its independent pullback contract; other v14 routes remain."""
    assert _V17.is_file(), "the v17 ETH pullback candidate is missing"
    prior = load_multi_asset_live_config(_V14, mode="observe")
    candidate = load_multi_asset_live_config(_V17, mode="observe")
    before = {provider.strategy_id: provider for provider in prior.providers}
    after = {provider.strategy_id: provider for provider in candidate.providers}

    assert candidate.profile_id == (
        "multi_asset_bidirectional_hype75_eth_pullback_routed_candidate_v17"
    )
    assert candidate.maximum_positions == prior.maximum_positions == 4
    assert candidate.assets == tuple(
        replace(asset, parent_profile_id=candidate.profile_id) for asset in prior.assets
    )
    assert candidate.executable_provider_symbols == {
        (_HULK, "BTC"),
        (_BREAKOUT, "BTC"),
        (_BREAKOUT, "SOL"),
        (_BREAKOUT, "HYPE"),
        (_ETH_PULLBACK, "ETH"),
    }
    assert after[_BREAKOUT] == replace(
        before[_BREAKOUT], execution_symbols=("BTC", "SOL", "HYPE")
    )
    assert after[_ETH_PULLBACK] == replace(
        before[_ETH_PULLBACK], execution_symbols=("ETH",)
    )
    assert all(
        after[strategy_id] == provider
        for strategy_id, provider in before.items()
        if strategy_id not in {_BREAKOUT, _ETH_PULLBACK}
    )


@pytest.mark.integration
def test_v17_preserves_bidirectional_risk_and_constructs_collectors() -> None:
    """The candidate retains audited risk and has every declared collector."""
    config = load_multi_asset_live_config(_V17, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}
    assets = {asset.symbol: asset for asset in config.assets}
    eth = providers[_ETH_PULLBACK]

    assert all(
        provider.sides == frozenset({"long", "short"})
        for provider in providers.values()
    )
    assert eth.execution.stop_bps == 60.0
    assert eth.execution.target_policy == "none"
    assert eth.execution.maximum_hold_seconds == 43_200
    assert assets["ETH"].max_notional_usd == 25.0
    assert assets["ETH"].leverage == 5.0
    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: None,
        backtest_lab_root=Path("../backtest-lab/backtest_lab").resolve(),
    )
    assert poller is not None


def test_v17_remains_fail_closed_without_live_authority() -> None:
    """A candidate profile cannot weaken the explicit live-start contract."""
    config = load_multi_asset_live_config(_V17, mode="live")

    with pytest.raises(MultiAssetLiveConfigError, match="--enabled"):
        config.require_live_start(credentials_present=True)
