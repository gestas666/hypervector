"""Contract tests for the GOLD-retired current-bankroll successor."""

from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_BASELINE = Path("configs/multi_asset_bidirectional_evidence_roster_canary_v36.toml")
_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_gold_retired_current_canary_v38.toml"
)


def test_v38_retires_only_gold_while_preserving_current_bankroll_sizing() -> None:
    """The immediate successor must not silently adopt the $5k notional ceilings."""
    baseline = load_multi_asset_live_config(_BASELINE, mode="observe")
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")

    assert (
        candidate.profile_id
        == "multi_asset_bidirectional_gold_retired_current_canary_v38"
    )
    assert candidate.maximum_positions == baseline.maximum_positions == 10
    assert candidate.symbols == tuple(
        symbol for symbol in baseline.symbols if symbol != "xyz:GOLD"
    )
    baseline_assets = {asset.symbol: asset for asset in baseline.assets}
    for asset in candidate.assets:
        expected = baseline_assets[asset.symbol]
        assert asset.margin_fraction == expected.margin_fraction
        assert asset.leverage == expected.leverage
        assert asset.max_notional_usd == expected.max_notional_usd
    assert candidate.executable_provider_symbols == {
        route
        for route in baseline.executable_provider_symbols
        if route[1] != "xyz:GOLD"
    }
    assert all("xyz:GOLD" not in provider.symbols for provider in candidate.providers)
    assert all(
        "xyz:GOLD" not in provider.execution_symbols for provider in candidate.providers
    )
