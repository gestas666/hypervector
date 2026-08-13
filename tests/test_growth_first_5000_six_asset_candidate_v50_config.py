"""Acceptance tests for the six-asset growth-first $5K successor."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.hip3_fresh15_journal_provider import (
    HIP3_INDEX_FRESH15_V3_STRATEGY,
    Hip3Fresh15JournalCollector,
)
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    load_multi_asset_live_config,
)

_V49 = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml")
_V50 = Path("configs/multi_asset_growth_first_5000_six_asset_candidate_v50.toml")
_HIP3 = HIP3_INDEX_FRESH15_V3_STRATEGY


def _asset_contract(asset: AssetLiveConfig) -> tuple[object, ...]:
    """Return execution fields that sizing/profile versioning may not alter."""
    return (
        asset.symbol,
        asset.sides,
        asset.leverage,
        asset.venue_max_leverage,
        asset.market_slippage_cap_fraction,
        asset.stop_bps,
        asset.maximum_hold_seconds,
        asset.margin_mode,
        asset.network,
    )


def test_v50_preserves_every_v49_core_provider_and_asset_contract() -> None:
    """The six-asset profile cannot alter repaired core strategy behavior."""
    baseline = load_multi_asset_live_config(_V49, mode="observe")
    candidate = load_multi_asset_live_config(_V50, mode="observe")
    baseline_providers = {row.strategy_id: row for row in baseline.providers}
    candidate_providers = {row.strategy_id: row for row in candidate.providers}
    candidate_assets = {row.symbol: row for row in candidate.assets}

    for strategy_id, provider in baseline_providers.items():
        assert candidate_providers[strategy_id] == provider
    for asset in baseline.assets:
        assert _asset_contract(candidate_assets[asset.symbol]) == _asset_contract(asset)


def test_v50_adds_exact_fresh15_index_route_and_six_asset_sizing() -> None:
    """The successor adds two executable index assets without hidden routes."""
    config = load_multi_asset_live_config(_V50, mode="observe")
    providers = {row.strategy_id: row for row in config.providers}
    assets = {row.symbol: row for row in config.assets}
    index = providers[_HIP3]

    assert config.maximum_positions == 10
    assert config.symbols == (
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SP500",
        "xyz:SPCX",
    )
    assert len(config.executable_provider_symbols) == 7
    assert len(config.executable_provider_directions) == 12
    assert {row.margin_fraction for row in assets.values()} == {0.10}
    assert {row.max_notional_usd for row in assets.values()} == {5_000.0}
    assert {row.leverage for row in assets.values()} == {10.0}
    assert sum(row.margin_fraction for row in assets.values()) == pytest.approx(0.60)
    assert index.symbols == ("xyz:SP500", "xyz:SPCX")
    assert index.execution_symbols == ("xyz:SP500", "xyz:SPCX")
    assert index.sides == frozenset({"long", "short"})
    assert index.execution.stop_bps == pytest.approx(80.0)
    assert index.execution.target_policy == "none"
    assert index.execution.maximum_hold_seconds == 86_400
    assert index.maximum_entry_delay_seconds == 30


def test_v50_index_route_uses_the_repaired_pressure_collector() -> None:
    """Both index symbols must resolve through the fresh-15-second collector."""
    config = load_multi_asset_live_config(_V50, mode="observe")
    provider = next(row for row in config.providers if row.strategy_id == _HIP3)

    collector = build_default_collector(provider, config, Path("backtest-lab"))

    assert isinstance(collector, Hip3Fresh15JournalCollector)
