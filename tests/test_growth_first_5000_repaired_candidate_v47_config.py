"""Acceptance tests for the repaired growth-first $5K candidate."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from hypervector.live.hip3_cohort_providers import Hip3BreakoutPressureCollector
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.research.v43_portfolio_friction_stress import (
    build_v43_portfolio_friction_stress,
)

_PROFILE = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v47.toml")
_RANGE = "range_onset_bidirectional_v1"
_FRICTION = Path(
    "data/logs/research/bidirectional_cohort/"
    "v46_execution_friction_stress_20260812_v1.json"
)
_VENUE = Path(
    "data/logs/research/bidirectional_cohort/"
    "v40_growth_sizing_stress_20260811T0200Z.json"
)


def test_v47_replaces_negative_ht_transfers_with_repaired_range_routes() -> None:
    """Only empirically surviving or versioned-repaired mechanisms remain."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}

    assert config.maximum_positions == 10
    assert config.symbols == ("BTC", "ETH", "SOL", "HYPE", "xyz:SP500")
    assert set(providers) == {
        "hulk_expansion_short_robust_v3",
        "liquidity_sweep_long_1h_stop60_target60_v2",
        _RANGE,
        "hype_breakout_compression_pullback_bidirectional_v1",
        "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v2",
    }
    assert "hype_breakout_onset_bidirectional_v1" not in providers
    assert providers[_RANGE].symbols == ("ETH", "SOL")
    assert providers[_RANGE].entry_context_overrides == (
        ("ETH", "dual_mtf_not_opposed"),
    )


def test_v47_uses_fixed_leverage_and_meaningful_after_friction_risk() -> None:
    """Notional, rather than leverage changes, expresses base route risk."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    assets = {asset.symbol: asset for asset in config.assets}

    assert {asset.leverage for asset in assets.values()} == {10.0}
    assert {asset.margin_fraction for asset in assets.values()} == {0.12}
    assert {asset.max_notional_usd for asset in assets.values()} == {6_000.0}
    assert sum(asset.margin_fraction for asset in assets.values()) == pytest.approx(
        0.60
    )

    base_notional = 5_000.0 * 0.12 * 10.0
    assert base_notional == pytest.approx(6_000.0)
    assert base_notional * 60.0 / 10_000.0 == pytest.approx(36.0)
    assert base_notional * 80.0 / 10_000.0 == pytest.approx(48.0)


def test_v47_preserves_mechanism_specific_exits() -> None:
    """Repairing route membership must not flatten distinct exit contracts."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}
    short = providers["hulk_expansion_short_robust_v3"].execution
    sweep = providers["liquidity_sweep_long_1h_stop60_target60_v2"].execution
    range_execution = providers[_RANGE].execution

    assert short.maximum_stop_bps == pytest.approx(75.0)
    assert short.target_r_multiple == pytest.approx(3.0)
    assert sweep.stop_bps == pytest.approx(60.0)
    assert sweep.target_bps == pytest.approx(60.0)
    assert range_execution.stop_bps == pytest.approx(60.0)
    assert range_execution.target_policy == "none"
    assert range_execution.maximum_hold_seconds == 172_800


def test_v47_corrected_hip3_route_is_executable_by_the_default_factory() -> None:
    """The v2 pressure identity must resolve to the fresh-15-second collector."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    provider = next(row for row in config.providers if "fresh15s" in row.strategy_id)

    collector = build_default_collector(provider, config, Path("backtest-lab"))

    assert isinstance(collector, Hip3BreakoutPressureCollector)
    assert collector.config.minimum_abs_imbalance == pytest.approx(0.1)


@pytest.mark.evidence
def test_v47_stress_scales_funding_to_each_provider_maximum_hold() -> None:
    """Forty-eight-hour Range routes must not be charged only 24h funding."""
    friction = json.loads(_FRICTION.read_text())["execution_friction_evidence"]
    report = build_v43_portfolio_friction_stress(
        _PROFILE,
        venue_stress_path=_VENUE,
        execution_friction=friction,
        account_values_usd=(5_000.0,),
        visible_depth_p99_bps={
            symbol: 1.0 for symbol in ("BTC", "ETH", "SOL", "HYPE", "xyz:SP500")
        },
    )
    slots = report["scenarios"][0]["asset_slots"]
    eth = slots["ETH"]["routes"][0]
    btc = slots["BTC"]["routes"][0]

    assert eth["maximum_hold_hours"] == pytest.approx(48.0)
    assert eth["friction_components_bps"]["adverse_maximum_hold_funding"] == (
        pytest.approx(1.399152)
    )
    assert btc["maximum_hold_hours"] == pytest.approx(24.0)
    assert btc["friction_components_bps"]["adverse_maximum_hold_funding"] == (
        pytest.approx(3.0)
    )


def test_v47_range_execution_contract_fails_closed_on_exit_drift(
    tmp_path: Path,
) -> None:
    """The historical 60bps/48h contract cannot silently become a new strategy."""
    exact = (
        'execution = { entry_liquidity = "taker_ioc", stop_policy = "fixed_bps", '
        'stop_bps = 60.0, target_policy = "none", maximum_hold_seconds = 172800 }'
    )
    changed = exact.replace("172800", "86400")
    profile = tmp_path / "range-exit-drift.toml"
    profile.write_text(_PROFILE.read_text().replace(exact, changed), encoding="utf-8")

    with pytest.raises(MultiAssetLiveConfigError, match="range onset"):
        load_multi_asset_live_config(profile, mode="observe")
