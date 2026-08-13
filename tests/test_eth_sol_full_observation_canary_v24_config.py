"""Four-asset observation contract for the ETH/SOL executable canary."""

from pathlib import Path

from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

PROFILE = Path(
    "configs/multi_asset_bidirectional_eth_sol_full_observation_canary_v24.toml"
)
ETH = "eth_breakout_precompression_pullback_bidirectional_v1"
RANGE = "range_onset_bidirectional_v1"


def test_v24_observes_four_assets_but_executes_only_eth_and_sol() -> None:
    """BTC/HYPE market telemetry must not acquire automatic order authority."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")

    assert config.profile_id == (
        "multi_asset_bidirectional_eth_sol_full_observation_canary_v24"
    )
    assert config.symbols == ("BTC", "ETH", "SOL", "HYPE")
    assert config.maximum_positions == 4
    assert config.executable_provider_symbols == {
        (ETH, "ETH"),
        (RANGE, "SOL"),
    }
    range_provider = next(
        provider for provider in config.providers if provider.strategy_id == RANGE
    )
    assert range_provider.symbols == ("BTC", "SOL", "HYPE")
    assert range_provider.execution_symbols == ("SOL",)


def test_v24_constructs_collectors_for_the_full_observation_roster() -> None:
    """Every visible provider-symbol route must have a production collector."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")

    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: None,
        backtest_lab_root=Path("../backtest-lab/backtest_lab").resolve(),
    )

    assert poller is not None
