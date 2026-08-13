"""Growth-first $5K successor configuration acceptance tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_strategy_evidence import strategy_evidence_payloads
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.hip3_cohort_providers import Hip3BreakoutPressureCollector

_PROFILE = Path("configs/multi_asset_growth_first_5000_candidate_v46.toml")


def test_v46_keeps_distinct_growth_routes_and_removes_failed_transfers() -> None:
    """The candidate retains usable mechanisms without carrying failed assets."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}

    assert config.maximum_positions == 10
    assert config.symbols == ("BTC", "ETH", "SOL", "HYPE", "xyz:SP500")
    assert set(providers) == {
        "hulk_expansion_short_robust_v3",
        "liquidity_sweep_long_1h_stop60_target60_v2",
        "hype_breakout_onset_bidirectional_v1",
        "hype_breakout_compression_pullback_bidirectional_v1",
        "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v2",
    }
    assert providers["hype_breakout_onset_bidirectional_v1"].sides == {
        "long",
        "short",
    }
    assert "hypervelocity_source_follow_bidirectional_5m_v1" not in providers
    assert "eth_breakout_precompression_pullback_bidirectional_v1" not in providers


def test_v46_base_notionals_target_meaningful_stop_risk() -> None:
    """Every asset must deploy a meaningful base notional at $5K equity."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    assets = {asset.symbol: asset for asset in config.assets}

    assert {symbol: asset.leverage for symbol, asset in assets.items()} == {
        "BTC": 10.0,
        "ETH": 10.0,
        "SOL": 10.0,
        "HYPE": 10.0,
        "xyz:SP500": 10.0,
    }

    def notional(symbol: str) -> float:
        asset = assets[symbol]
        return min(
            5_000.0 * asset.margin_fraction * asset.leverage,
            asset.max_notional_usd,
        )

    assert notional("ETH") == pytest.approx(4_000.0)
    assert notional("SOL") == pytest.approx(4_000.0)
    assert notional("HYPE") == pytest.approx(4_000.0)
    assert notional("xyz:SP500") == pytest.approx(4_500.0)


def test_v46_fresh15_route_resolves_to_the_versioned_live_collector() -> None:
    """The corrected identity must be executable through the default factory."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    provider = next(row for row in config.providers if "fresh15s" in row.strategy_id)

    collector = build_default_collector(provider, config, Path("backtest-lab"))

    assert isinstance(collector, Hip3BreakoutPressureCollector)
    assert collector.config.minimum_abs_imbalance == pytest.approx(0.1)


def test_v46_fresh15_route_discloses_v1_contamination_and_v2_uncertainty() -> None:
    """The cockpit must not relabel the corrected route as already profitable."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    evidence = next(
        row
        for row in strategy_evidence_payloads(config.providers)
        if "fresh15s" in str(row["strategy_id"])
    )

    assert evidence["research_state"] == ("fresh15_v2_parity_defect_retired")
    assert "parity remained broken" in str(evidence["cadence"])
    assert "retired from qualification" in str(evidence["summary"])
    assert str(evidence["evidence_source"]).endswith(
        "hip3-index-preclose-pressure-parity-v3.json"
    )


def test_v46_btc_specialists_and_route_exits_remain_exact() -> None:
    """Growth sizing must not mutate entry or exit mechanisms."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}
    short = providers["hulk_expansion_short_robust_v3"]
    long = providers["liquidity_sweep_long_1h_stop60_target60_v2"]
    onset = providers["hype_breakout_onset_bidirectional_v1"]

    assert short.execution.maximum_stop_bps == pytest.approx(75.0)
    assert short.execution.target_r_multiple == pytest.approx(3.0)
    assert long.execution.stop_bps == pytest.approx(60.0)
    assert long.execution.target_bps == pytest.approx(60.0)
    assert onset.symbols == ("ETH", "SOL")
    assert onset.execution.maximum_hold_policy == "extend_while_regime_supported"
    assert onset.execution.maximum_hold_seconds == 28_800
    assert onset.execution.hard_maximum_hold_seconds == 86_400


def test_v46_full_base_book_uses_less_than_half_initial_margin() -> None:
    """Five simultaneous base positions must leave expansion headroom."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    margin = sum(5_000.0 * asset.margin_fraction for asset in config.assets)

    assert margin == pytest.approx(2_150.0)
    assert margin / 5_000.0 == pytest.approx(0.43)
