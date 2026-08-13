"""Contract tests for the inactive lean successor v30 candidate."""

from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

PROFILE = Path("configs/multi_asset_bidirectional_lean_successor_canary_v30.toml")
RANGE = "range_onset_bidirectional_v1"
SPCX = "hip3_swing_ha_sp500_spcx_bidirectional_v2"


def test_v30_contains_only_three_evidence_selected_bidirectional_routes() -> None:
    """The inactive candidate must omit the rejected broad-profile filler."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")

    assert config.profile_id == "multi_asset_bidirectional_lean_successor_canary_v30"
    assert config.symbols == ("ETH", "SOL", "xyz:SPCX")
    assert config.maximum_positions == len(config.assets) == 3
    assert config.executable_provider_symbols == {
        (RANGE, "ETH"),
        (RANGE, "SOL"),
        (SPCX, "xyz:SPCX"),
    }
    observed = {
        (provider.strategy_id, symbol)
        for provider in config.providers
        for symbol in provider.symbols
    }
    assert observed == config.executable_provider_symbols
    assert all(
        provider.executable_sides(symbol) == frozenset({"long", "short"})
        for provider in config.providers
        for symbol in provider.execution_symbols
    )


def test_v30_preserves_measured_context_risk_and_exit_contracts() -> None:
    """Route selection may not silently change sizing or lifecycle mechanics."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}
    assets = {asset.symbol: asset for asset in config.assets}

    range_provider = providers[RANGE]
    assert range_provider.entry_context_overrides == (("ETH", "dual_mtf_not_opposed"),)
    assert range_provider.execution.stop_bps == 60.0
    assert range_provider.execution.maximum_hold_seconds == 172_800
    assert range_provider.execution.provider_recipe_exit_policy == "ignore"

    spcx = providers[SPCX]
    assert spcx.execution.stop_bps == 80.0
    assert spcx.execution.maximum_hold_seconds == 86_400
    assert spcx.execution.provider_recipe_exit_policy == "ignore"

    assert assets["ETH"].max_notional_usd == 25.0
    assert assets["SOL"].max_notional_usd == 75.0
    assert assets["xyz:SPCX"].max_notional_usd == 75.0
    assert all(asset.leverage == 5.0 for asset in assets.values())
