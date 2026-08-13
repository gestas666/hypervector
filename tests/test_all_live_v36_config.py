"""Exact roster contract for the post-v35 $500 live-research profile."""

from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_PROFILE = Path("configs/multi_asset_bidirectional_evidence_roster_canary_v36.toml")
_RANGE = "range_onset_bidirectional_v1"
_HIP3_SWING = {
    "hip3_swing_ha_sp500_spcx_bidirectional_v2",
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
}
_HIP3_BREAKOUT = {
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1": (
        "xyz:SP500",
        "xyz:SPCX",
    ),
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1": (
        "xyz:SNDK",
        "xyz:GOLD",
        "xyz:BRENTOIL",
    ),
}


def test_v36_keeps_only_explicitly_executable_provider_symbols() -> None:
    """The successor contains no strategy route that is merely observe-only."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}

    assert config.profile_id == "multi_asset_bidirectional_evidence_roster_canary_v36"
    assert config.maximum_positions == 10
    assert len(config.assets) == 9
    assert not (_HIP3_SWING & providers.keys())
    assert providers[_RANGE].symbols == ("SOL",)
    assert providers[_RANGE].execution_symbols == ("SOL",)
    for strategy, symbols in _HIP3_BREAKOUT.items():
        assert providers[strategy].symbols == symbols
        assert providers[strategy].execution_symbols == symbols
    assert all(
        provider.execution_symbols == provider.symbols for provider in config.providers
    )


def test_v36_preserves_v35_assets_sizing_and_bidirectional_authority() -> None:
    """Roster cleanup cannot silently resize or remove a portfolio asset side."""
    prior = load_multi_asset_live_config(
        Path("configs/multi_asset_bidirectional_all_live_canary_v35.toml"),
        mode="observe",
    )
    candidate = load_multi_asset_live_config(_PROFILE, mode="observe")

    fields = (
        "symbol",
        "sides",
        "leverage",
        "venue_max_leverage",
        "margin_fraction",
        "max_notional_usd",
        "market_slippage_cap_fraction",
        "stop_bps",
        "maximum_hold_seconds",
    )
    assert [
        tuple(getattr(asset, field) for field in fields) for asset in candidate.assets
    ] == [tuple(getattr(asset, field) for field in fields) for asset in prior.assets]
    assert candidate.symbols == prior.symbols
    assert all(
        provider.sides == frozenset({"long", "short"})
        for provider in candidate.providers
    )
    assert len(candidate.executable_provider_symbols) == 16
