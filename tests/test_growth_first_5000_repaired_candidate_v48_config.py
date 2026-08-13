"""Acceptance tests for the evidence-pruned growth-first $5K candidate."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config


_PROFILE = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v48.toml")
_RANGE = "range_onset_bidirectional_v1"
_STRESS = Path(
    "data/logs/research/bidirectional_cohort/v48_growth_sizing_stress_20260812_v1.json"
)


def test_v48_removes_negative_sp500_without_reducing_total_margin_budget() -> None:
    """The successor reallocates the retired slot only across retained assets."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}
    assets = {asset.symbol: asset for asset in config.assets}

    assert config.maximum_positions == 10
    assert config.symbols == ("BTC", "ETH", "SOL", "HYPE")
    assert len(config.executable_provider_symbols) == 5
    assert set(providers) == {
        "hulk_expansion_short_robust_v3",
        "liquidity_sweep_long_1h_stop60_target60_v2",
        _RANGE,
        "hype_breakout_compression_pullback_bidirectional_v1",
    }
    assert not any("hip3" in strategy for strategy in providers)
    assert {asset.margin_fraction for asset in assets.values()} == {0.15}
    assert {asset.max_notional_usd for asset in assets.values()} == {7_500.0}
    assert sum(asset.margin_fraction for asset in assets.values()) == pytest.approx(0.6)


def test_v48_preserves_each_retained_mechanism_and_fixed_leverage() -> None:
    """Pruning one route must not silently alter the surviving strategies."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}

    assert {asset.leverage for asset in config.assets} == {10.0}
    assert providers[_RANGE].entry_context_overrides == (
        ("ETH", "dual_mtf_not_opposed"),
    )
    assert providers["hulk_expansion_short_robust_v3"].execution.target_r_multiple == (
        pytest.approx(3.0)
    )
    sweep = providers["liquidity_sweep_long_1h_stop60_target60_v2"].execution
    assert sweep.stop_bps == pytest.approx(60.0)
    assert sweep.target_bps == pytest.approx(60.0)
    assert providers[_RANGE].execution.maximum_hold_seconds == 172_800
    compression = providers[
        "hype_breakout_compression_pullback_bidirectional_v1"
    ].execution
    assert compression.maximum_hold_seconds == 28_800
    assert compression.hard_maximum_hold_seconds == 86_400


def test_v48_stress_matches_four_slot_sixty_percent_growth_contract() -> None:
    """The exact candidate-size stress must bind the pruned route topology."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    report = json.loads(_STRESS.read_text(encoding="utf-8"))
    scenario = next(
        row for row in report["scenarios"] if row["account_value_usd"] == 5_000.0
    )

    assert report["profile_id"] == config.profile_id
    assert report["profile_fingerprint"] == config.profile_fingerprint
    assert scenario["maximum_simultaneous_positions"] == 4
    assert scenario["route_aware_maximum_margin_fraction"] == pytest.approx(0.6)
    assert scenario["stacked_p99_stop_wave_loss_usd"] == pytest.approx(
        294.7042017546197
    )
    assert scenario["stacked_p99_stop_wave_loss_pct_equity"] == pytest.approx(
        5.894084035092394
    )
    assert set(scenario["asset_slots"]) == {"BTC", "ETH", "SOL", "HYPE"}
    assert {
        route["planned_notional_usd"]
        for slot in scenario["asset_slots"].values()
        for route in slot["routes"]
    } == {7_500.0}
