"""Corrected BTC-specialist successor contract and provider wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.btc_liquidity_sweep_long_provider import (
    LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY,
    LiquiditySweepLongCollector,
)
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_polling_contract import (
    READINESS_SEED_LOOKBACK_MINUTES,
    SOURCE_TIMEFRAMES,
)
from hypervector.live.multi_asset_strategy_evidence import strategy_evidence_payloads

_PROFILE = Path(
    "configs/multi_asset_bidirectional_btc_specialists_corrected_candidate_v44.toml"
)


def test_v44_uses_corrected_taker_parity_long_without_rewriting_v43() -> None:
    """The corrected route has a distinct identity and immutable predecessor."""
    assert Path(
        "configs/multi_asset_bidirectional_btc_specialists_candidate_v43.toml"
    ).is_file()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}

    assert LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY in providers
    assert "liquidity_sweep_long_1h_stop60_v1" not in providers
    long = providers[LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY]
    assert long.maximum_entry_delay_seconds == 30
    assert long.execution.entry_liquidity == "taker_ioc"
    assert long.execution.stop_bps == pytest.approx(60.0)
    assert long.execution.target_bps == pytest.approx(60.0)
    assert long.execution.maximum_hold_seconds == 86_400


def test_v44_corrected_long_has_runtime_collector_and_clock_contract() -> None:
    """The new route identity reaches the existing causal signal implementation."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY
    )
    collector = build_default_collector(provider, config, Path("backtest-lab"))

    assert isinstance(collector, LiquiditySweepLongCollector)
    assert collector.strategy_id == LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY
    assert SOURCE_TIMEFRAMES[LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY] == "1m"
    assert READINESS_SEED_LOOKBACK_MINUTES[LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY] == 61


def test_v44_evidence_discloses_taker_challenger_and_unresolved_path() -> None:
    """Cockpit evidence cannot relabel maker fills as causal taker execution."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    rows = {
        (str(row["strategy_id"]), str(row["symbol"])): row
        for row in strategy_evidence_payloads(config.providers)
    }
    evidence = rows[(LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY, "BTC")]

    assert evidence["research_state"] == "taker_parity_promising_path_unresolved"
    assert "5W/1L" in str(evidence["summary"])
    assert "maker" in str(evidence["summary"]).lower()
    assert "unresolved" in str(evidence["summary"]).lower()
    assert str(evidence["evidence_source"]).endswith(
        "btc_liquidity_sweep_taker_parity_20260811_v2.json"
    )
