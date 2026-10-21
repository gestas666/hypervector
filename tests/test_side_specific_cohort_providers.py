"""Aggregate bidirectional coverage for side-specific cohort providers."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError

_BASE = Path("tests/fixtures/profiles/three_asset_bidirectional.toml")
_BIDIRECTIONAL_BLOCK = """[[providers]]
strategy_id = "test_trend_5m"
symbols = ["BTC"]
sides = ["long", "short"]
priority = 10
timeframe = "5m"
maximum_entry_delay_seconds = 60
execution_symbols = ["BTC"]
execution = { entry_liquidity = "taker_ioc", stop_policy = "structural_clamped_bps", minimum_stop_bps = 20.0, maximum_stop_bps = 75.0, target_policy = "reward_risk", target_r_multiple = 3.0, maximum_hold_seconds = 86400 }
"""
_SIDE_SPECIFIC_BLOCKS = """[[providers]]
strategy_id = "test_short_trend_5m"
symbols = ["BTC"]
sides = ["short"]
priority = 20
timeframe = "5m"
maximum_entry_delay_seconds = 60
execution_symbols = ["BTC"]
execution = { entry_liquidity = "taker_ioc", stop_policy = "structural_clamped_bps", minimum_stop_bps = 20.0, maximum_stop_bps = 75.0, target_policy = "reward_risk", target_r_multiple = 3.0, maximum_hold_seconds = 86400 }

[[providers]]
strategy_id = "test_long_stop_1m"
symbols = ["BTC"]
sides = ["long"]
priority = 10
timeframe = "1m"
maximum_entry_delay_seconds = 60
execution_symbols = ["BTC"]
execution = { entry_liquidity = "taker_ioc", stop_policy = "fixed_bps", stop_bps = 60.0, target_policy = "fixed_bps", target_bps = 26.666666666666668, maximum_hold_seconds = 86400 }
"""


def test_side_specific_providers_may_jointly_supply_bidirectional_coverage(
    tmp_path: Path,
) -> None:
    """The asset stays bidirectional while each strategy keeps honest scope."""
    text = _BASE.read_text(encoding="utf-8").replace(
        _BIDIRECTIONAL_BLOCK,
        _SIDE_SPECIFIC_BLOCKS,
    )
    profile = tmp_path / "side-specific.toml"
    profile.write_text(text, encoding="utf-8")

    config = load_multi_asset_live_config(profile, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}

    assert providers["test_short_trend_5m"].sides == {"short"}
    assert providers["test_long_stop_1m"].sides == {"long"}
    assert (
        "test_short_trend_5m",
        "BTC",
        "short",
    ) in config.executable_provider_directions
    assert (
        "test_long_stop_1m",
        "BTC",
        "long",
    ) in config.executable_provider_directions


def test_shared_market_entry_adapter_rejects_maker_only_provider_claims(
    tmp_path: Path,
) -> None:
    """A config cannot advertise maker execution that the engine cannot submit."""
    profile = tmp_path / "false-maker-contract.toml"
    profile.write_text(
        _BASE.read_text(encoding="utf-8").replace(
            'entry_liquidity = "taker_ioc"',
            'entry_liquidity = "maker_post_only"',
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(MultiAssetLiveConfigError, match="market entry adapter"):
        load_multi_asset_live_config(profile, mode="observe")


