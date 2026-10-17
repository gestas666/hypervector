"""Acceptance contract for the incremental eight-asset v58 successor."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_default_collectors import build_default_collector


_V58 = Path("configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml")
_ETH = "eth_breakout_precompression_pullback_bidirectional_v1"
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_HYPE = "hype_breakout_compression_alignment_bidirectional_v2"
_INDEX = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3"
_SPCX = "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1"
_COMMODITY = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"


def _config() -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(_V58, mode="observe")


def test_v58_has_exact_four_crypto_four_noncrypto_live_roster() -> None:
    """Every requested asset has explicit execution authority and one slot."""
    config = _config()

    assert (
        config.profile_id == "multi_asset_growth_first_5000_eight_asset_incremental_v58"
    )
    assert config.maximum_positions == 10
    assert config.symbols == (
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SP500",
        "xyz:SPCX",
        "xyz:SNDK",
        "xyz:BRENTOIL",
    )
    assert {symbol for _, symbol in config.executable_provider_symbols} == set(
        config.symbols
    )


def test_v58_uses_evidence_tiered_growth_sizing() -> None:
    """Incumbents remain meaningful while weaker trials have bounded exposure."""
    assets = {asset.symbol: asset for asset in _config().assets}
    expected = {
        "BTC": (10.0, 0.10, 5_000.0),
        "HYPE": (10.0, 0.10, 5_000.0),
        "xyz:SP500": (5.0, 0.07, 1_750.0),
        "xyz:SPCX": (5.0, 0.07, 1_750.0),
        "ETH": (5.0, 0.03, 750.0),
        "SOL": (5.0, 0.03, 750.0),
        "xyz:SNDK": (5.0, 0.03, 750.0),
        "xyz:BRENTOIL": (5.0, 0.03, 750.0),
    }

    assert {
        symbol: (row.leverage, row.margin_fraction, row.max_notional_usd)
        for symbol, row in assets.items()
    } == expected
    assert sum(row.margin_fraction for row in assets.values()) == pytest.approx(0.46)


def test_v58_freezes_incremental_route_and_exit_contracts() -> None:
    """The successor reuses named mechanisms without cross-asset HYPE transfer."""
    config = _config()
    providers = {provider.strategy_id: provider for provider in config.providers}

    assert "hype_breakout_onset_bidirectional_v1" not in providers
    assert providers[_HULK].symbols == providers[_HULK].execution_symbols == ("SOL",)
    assert providers[_HULK].executable_sides("SOL") == frozenset({"short"})
    assert providers[_ETH].executable_sides("ETH") == frozenset({"long", "short"})
    assert providers[_HYPE].executable_sides("HYPE") == frozenset({"long", "short"})
    assert (
        providers[_INDEX].symbols
        == providers[_INDEX].execution_symbols
        == ("xyz:SP500",)
    )
    assert providers[_INDEX].executable_sides("xyz:SP500") == frozenset(
        {"long", "short"}
    )
    index_exit = providers[_INDEX].execution
    assert (
        index_exit.profit_lock_policy,
        index_exit.profit_lock_activation_bps,
        index_exit.profit_lock_floor_bps,
        index_exit.profit_lock_giveback_bps,
    ) == ("completed_bar_trailing", 100.0, 40.0, 80.0)
    assert providers[_SPCX].executable_sides("xyz:SPCX") == frozenset({"short"})
    assert (
        providers[_COMMODITY].symbols
        == providers[_COMMODITY].execution_symbols
        == (
            "xyz:SNDK",
            "xyz:BRENTOIL",
        )
    )
    assert providers[_COMMODITY].executable_sides("xyz:SNDK") == frozenset({"short"})
    assert providers[_COMMODITY].executable_sides("xyz:BRENTOIL") == frozenset(
        {"long", "short"}
    )


def test_v58_has_no_observe_only_route_or_uncovered_side() -> None:
    """All eight assets are executable while aggregate side coverage stays explicit."""
    config = _config()

    assert all(provider.execution_symbols for provider in config.providers)
    assert len(config.executable_provider_symbols) == 10
    assert len(config.executable_provider_directions) == 14


@pytest.mark.integration
def test_v58_constructs_every_declared_runtime_collector() -> None:
    """A validated route must also resolve to a concrete runtime collector."""
    config = _config()
    root = Path("../backtest-lab/backtest_lab")

    collectors = {
        provider.strategy_id: build_default_collector(provider, config, root)
        for provider in config.providers
    }

    assert set(collectors) == {provider.strategy_id for provider in config.providers}
    assert all(callable(collector) for collector in collectors.values())
