"""Contract for the evidence-selected inactive v29 portfolio candidate."""

from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

PROFILE = Path(
    "configs/multi_asset_bidirectional_evidence_selected_portfolio_canary_v29.toml"
)
RANGE = "range_onset_bidirectional_v1"
ETH_PULLBACK = "eth_breakout_precompression_pullback_bidirectional_v1"
SWING_INDEX = "hip3_swing_ha_sp500_spcx_bidirectional_v2"
BREAKOUT_INDEX = "hip3_breakout_pressure_sp500_spcx_bidirectional_v1"
SWING_COMMODITY = "hip3_swing_ha_sndk_gold_brent_bidirectional_v1"


def test_v29_executes_only_the_six_selected_bidirectional_routes() -> None:
    """The candidate must not retain evidence-negative or observation-only filler."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")

    expected = {
        (RANGE, "ETH"),
        (RANGE, "SOL"),
        (ETH_PULLBACK, "ETH"),
        (SWING_INDEX, "xyz:SPCX"),
        (BREAKOUT_INDEX, "xyz:SP500"),
        (SWING_COMMODITY, "xyz:GOLD"),
    }
    observed = {
        (provider.strategy_id, symbol)
        for provider in config.providers
        for symbol in provider.symbols
    }

    assert config.profile_id == (
        "multi_asset_bidirectional_evidence_selected_portfolio_canary_v29"
    )
    assert config.symbols == (
        "ETH",
        "SOL",
        "xyz:SP500",
        "xyz:SPCX",
        "xyz:GOLD",
    )
    assert config.maximum_positions == len(config.assets) == 5
    assert config.executable_provider_symbols == expected
    assert observed == expected
    assert all(
        provider.sides == frozenset({"long", "short"}) for provider in config.providers
    )


def test_v29_preserves_exact_route_risk_and_context_contracts() -> None:
    """Selection cannot silently change the mechanisms that supplied evidence."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}

    range_provider = providers[RANGE]
    assert range_provider.entry_context_overrides == (("ETH", "dual_mtf_not_opposed"),)
    assert range_provider.execution.stop_bps == 60.0
    assert range_provider.execution.maximum_hold_seconds == 172_800

    pullback = providers[ETH_PULLBACK]
    assert pullback.execution.stop_bps == 60.0
    assert pullback.execution.maximum_hold_seconds == 43_200

    for strategy_id in (SWING_INDEX, BREAKOUT_INDEX, SWING_COMMODITY):
        contract = providers[strategy_id].execution
        assert contract.stop_bps == 80.0
        assert contract.maximum_hold_seconds == 86_400

    assets = {asset.symbol: asset for asset in config.assets}
    assert assets["ETH"].max_notional_usd == 25.0
    assert assets["SOL"].max_notional_usd == 75.0
    assert all(
        assets[symbol].max_notional_usd == 75.0
        for symbol in ("xyz:SP500", "xyz:SPCX", "xyz:GOLD")
    )
