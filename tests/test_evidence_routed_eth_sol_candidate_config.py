"""Contract tests for the inactive ETH/SOL evidence-routed candidate."""

from __future__ import annotations

import pytest

from pathlib import Path

from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_PROFILE = Path(
    "tests/fixtures/profiles/multi_asset_bidirectional_eth_pullback_sol_range_candidate_v15.toml"
)
_ETH = "eth_breakout_precompression_pullback_bidirectional_v1"
_SOL = "range_onset_bidirectional_v1"


def test_v15_routes_only_independent_eth_and_sol_candidates() -> None:
    """The candidate must not carry the rejected cross-asset breakout routes."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {row.strategy_id: row for row in config.providers}

    assert config.profile_id == (
        "multi_asset_bidirectional_eth_pullback_sol_range_candidate_v15"
    )
    assert config.maximum_positions == 4
    assert config.executable_provider_symbols == {
        (_ETH, "ETH"),
        (_SOL, "SOL"),
    }
    assert all(
        provider.sides == frozenset({"long", "short"})
        for provider in providers.values()
    )


def test_v15_preserves_audited_exit_and_risk_shapes() -> None:
    """Each candidate must retain the exact historical contract it represents."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {row.strategy_id: row for row in config.providers}
    assets = {row.symbol: row for row in config.assets}

    eth = providers[_ETH]
    assert eth.execution.stop_bps == 60.0
    assert eth.execution.target_policy == "none"
    assert eth.execution.maximum_hold_seconds == 43_200
    assert assets["ETH"].max_notional_usd == 25.0
    assert assets["ETH"].leverage == 5.0

    sol = providers[_SOL]
    assert sol.execution.stop_bps == 60.0
    assert sol.execution.target_policy == "none"
    assert sol.execution.maximum_hold_seconds == 172_800
    assert assets["SOL"].max_notional_usd == 75.0
    assert assets["SOL"].leverage == 5.0


@pytest.mark.integration
def test_v15_constructs_every_declared_provider() -> None:
    """An inactive profile is invalid if any declared collector is unavailable."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")

    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: None,
        backtest_lab_root=Path("../backtest-lab/backtest_lab").resolve(),
    )

    assert poller is not None
