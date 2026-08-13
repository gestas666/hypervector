"""Acceptance tests for the profit-protected six-asset $5K successor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.live.hip3_fresh15_journal_provider import (
    HIP3_INDEX_FRESH15_V3_STRATEGY,
    Hip3Fresh15JournalCollector,
)
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_V49 = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml")
_V51 = Path(
    "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
)
_HIP3 = HIP3_INDEX_FRESH15_V3_STRATEGY
_STRESS = Path("tests/fixtures/v51_growth_sizing_stress_5000.json")
_CORE = {
    "hulk_expansion_short_robust_v3",
    "liquidity_sweep_long_1h_stop60_target60_v2",
    "range_onset_bidirectional_v1",
    "hype_breakout_compression_pullback_bidirectional_v1",
}


def test_v51_preserves_repaired_core_and_six_asset_growth_scope() -> None:
    """Only the index exit contract may differ from repaired v49 core."""
    baseline = load_multi_asset_live_config(_V49, mode="observe")
    candidate = load_multi_asset_live_config(_V51, mode="observe")
    baseline_providers = {row.strategy_id: row for row in baseline.providers}
    candidate_providers = {row.strategy_id: row for row in candidate.providers}

    assert all(candidate_providers[key] == baseline_providers[key] for key in _CORE)
    assert candidate.symbols == (
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SP500",
        "xyz:SPCX",
    )
    assert candidate.maximum_positions == 10
    assert len(candidate.executable_provider_symbols) == 7
    assert len(candidate.executable_provider_directions) == 12
    assert sum(row.margin_fraction for row in candidate.assets) == pytest.approx(0.60)
    assert {row.max_notional_usd for row in candidate.assets} == {5_000.0}
    assert {row.leverage for row in candidate.assets} == {10.0}


def test_v51_index_contract_locks_profit_without_capping_winners() -> None:
    """Every index side keeps its stop and gains a symmetric trailing lock."""
    config = load_multi_asset_live_config(_V51, mode="observe")
    provider = next(row for row in config.providers if row.strategy_id == _HIP3)

    assert provider.execution.stop_bps == pytest.approx(80.0)
    assert provider.execution.target_policy == "none"
    assert provider.execution.maximum_hold_seconds == 86_400
    for symbol in ("xyz:SP500", "xyz:SPCX"):
        for side in ("long", "short"):
            contract = provider.execution_for(symbol, side)
            assert contract.profit_lock_policy == "completed_bar_trailing"
            assert contract.profit_lock_activation_bps == pytest.approx(100.0)
            assert contract.profit_lock_floor_bps == pytest.approx(40.0)
            assert contract.profit_lock_giveback_bps == pytest.approx(80.0)


def test_v51_index_route_keeps_the_repaired_pressure_collector() -> None:
    """Profit protection cannot change the index entry-signal implementation."""
    config = load_multi_asset_live_config(_V51, mode="observe")
    provider = next(row for row in config.providers if row.strategy_id == _HIP3)

    collector = build_default_collector(provider, config, Path("backtest-lab"))

    assert isinstance(collector, Hip3Fresh15JournalCollector)


def test_v51_stress_is_bound_to_the_exact_profit_protected_profile() -> None:
    """The $5K launch must not reuse the superseded v50 identity."""
    config = load_multi_asset_live_config(_V51, mode="observe")
    report = json.loads(_STRESS.read_text(encoding="utf-8"))
    scenario = next(
        row for row in report["scenarios"] if row["account_value_usd"] == 5_000.0
    )

    assert report["profile_id"] == config.profile_id
    assert report["profile_fingerprint"] == config.profile_fingerprint
    assert scenario["maximum_simultaneous_positions"] == 6
    assert scenario["route_aware_maximum_margin_fraction"] == pytest.approx(0.60)
    assert scenario["stacked_p99_stop_wave_loss_usd"] == pytest.approx(299.152584)
    assert scenario["stacked_p99_stop_wave_loss_pct_equity"] == pytest.approx(5.983052)
