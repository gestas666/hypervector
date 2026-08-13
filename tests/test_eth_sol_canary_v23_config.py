"""Executable routing contract for the evidence-backed ETH/SOL canary."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)

PROFILE = Path("configs/multi_asset_bidirectional_eth_sol_canary_v23.toml")
ETH = "eth_breakout_precompression_pullback_bidirectional_v1"
SOL = "range_onset_bidirectional_v1"


def test_v23_contains_only_two_bidirectional_executable_routes() -> None:
    """Known-negative and observation-only providers must not enter v23."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")

    assert config.profile_id == "multi_asset_bidirectional_eth_sol_canary_v23"
    assert config.symbols == ("ETH", "SOL")
    assert config.maximum_positions == 2
    assert config.executable_provider_symbols == {
        (ETH, "ETH"),
        (SOL, "SOL"),
    }
    assert config.executable_provider_directions == {
        (ETH, "ETH", "long"),
        (ETH, "ETH", "short"),
        (SOL, "SOL", "long"),
        (SOL, "SOL", "short"),
    }
    assert {provider.strategy_id for provider in config.providers} == {ETH, SOL}


def test_v23_matches_the_joint_replay_risk_and_exit_contract() -> None:
    """Live sizing and lifecycle controls must match the replayed profile."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")
    assets = {asset.symbol: asset for asset in config.assets}
    providers = {provider.strategy_id: provider for provider in config.providers}

    assert assets["ETH"].leverage == 5.0
    assert assets["ETH"].max_notional_usd == 25.0
    assert assets["ETH"].stop_bps == 60.0
    assert assets["ETH"].maximum_hold_seconds == 43_200
    assert providers[ETH].execution.stop_bps == 60.0
    assert providers[ETH].execution.maximum_hold_seconds == 43_200
    assert providers[ETH].execution.target_policy == "none"

    assert assets["SOL"].leverage == 5.0
    assert assets["SOL"].max_notional_usd == 75.0
    assert assets["SOL"].stop_bps == 60.0
    assert assets["SOL"].maximum_hold_seconds == 172_800
    assert providers[SOL].execution.stop_bps == 60.0
    assert providers[SOL].execution.maximum_hold_seconds == 172_800
    assert providers[SOL].execution.target_policy == "none"


def test_v23_remains_fail_closed_without_both_live_flags() -> None:
    """The candidate cannot acquire order authority through config alone."""
    disabled = load_multi_asset_live_config(
        PROFILE,
        mode="live",
        enabled=False,
        accepts_live_risk=True,
    )
    with pytest.raises(MultiAssetLiveConfigError, match="--enabled"):
        disabled.require_live_start(credentials_present=True)
    unaccepted = load_multi_asset_live_config(
        PROFILE,
        mode="live",
        enabled=True,
        accepts_live_risk=False,
    )
    with pytest.raises(MultiAssetLiveConfigError, match="--i-accept-live-risk"):
        unaccepted.require_live_start(credentials_present=True)


def test_v23_constructs_each_declared_live_collector() -> None:
    """Every executable route must have a production collector implementation."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")

    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: None,
        backtest_lab_root=Path("../backtest-lab/backtest_lab").resolve(),
    )

    assert poller is not None
