"""Acceptance tests for the evidence-bound $5K v52 successor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.live.bidirectional_intents import (
    BidirectionalIntentRouter,
    PositionState,
    StrategyCapability,
    StrategyIntent,
)
from hypervector.live.btc_hulk_robust_short_provider import (
    HulkRobustShortCollector,
)
from hypervector.live.btc_liquidity_sweep_long_provider import (
    LiquiditySweepLongCollector,
)
from hypervector.live.hype_compression_alignment_provider import (
    HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
    HypeCompressionAlignmentCollector,
)
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_PROFILE = Path(
    "configs/multi_asset_growth_first_5000_evidence_bound_successor_v52.toml"
)
_HULK = "hulk_expansion_short_robust_v3"
_SWEEP = "liquidity_sweep_long_1h_stop60_target60_v2"
_STRESS = Path("tests/fixtures/v52_growth_sizing_stress_5000.json")


def test_v52_has_only_evidence_supported_execution_routes() -> None:
    """Retired Range and unresolved HIP-3 routes cannot retain authority."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")

    assert config.symbols == ("BTC", "HYPE")
    assert config.maximum_positions == 10
    assert config.executable_provider_symbols == frozenset(
        {
            (_HULK, "BTC"),
            (_SWEEP, "BTC"),
            (HYPE_COMPRESSION_ALIGNMENT_STRATEGY, "HYPE"),
        }
    )
    assert config.executable_provider_directions == frozenset(
        {
            (_HULK, "BTC", "short"),
            (_SWEEP, "BTC", "long"),
            (HYPE_COMPRESSION_ALIGNMENT_STRATEGY, "HYPE", "long"),
            (HYPE_COMPRESSION_ALIGNMENT_STRATEGY, "HYPE", "short"),
        }
    )
    assert sum(asset.margin_fraction for asset in config.assets) == pytest.approx(0.20)
    assert {asset.leverage for asset in config.assets} == {10.0}
    assert {asset.max_notional_usd for asset in config.assets} == {5_000.0}


def test_v52_preserves_exact_route_exit_contracts() -> None:
    """Each selected route must retain its evidence-matched stop and exit."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}

    hulk = providers[_HULK].execution
    assert hulk.stop_policy == "structural_clamped_bps"
    assert (hulk.minimum_stop_bps, hulk.maximum_stop_bps) == pytest.approx((20, 75))
    assert hulk.target_policy == "reward_risk"
    assert hulk.target_r_multiple == pytest.approx(3.0)
    assert hulk.maximum_hold_seconds == 86_400

    sweep = providers[_SWEEP].execution
    assert sweep.stop_bps == pytest.approx(60.0)
    assert sweep.target_bps == pytest.approx(60.0)
    assert sweep.maximum_hold_seconds == 86_400

    hype = providers[HYPE_COMPRESSION_ALIGNMENT_STRATEGY].execution
    assert hype.stop_bps == pytest.approx(80.0)
    assert hype.target_policy == "none"
    assert hype.maximum_hold_policy == "extend_while_regime_supported"
    assert hype.maximum_hold_seconds == 28_800
    assert hype.hard_maximum_hold_seconds == 86_400


def test_v52_builds_the_exact_three_live_collectors() -> None:
    """Every configured route must resolve to its versioned implementation."""
    config = load_multi_asset_live_config(_PROFILE, mode="live")
    collectors = {
        provider.strategy_id: build_default_collector(
            provider,
            config,
            Path("../backtest-lab/backtest_lab"),
        )
        for provider in config.providers
    }

    assert isinstance(collectors[_HULK], HulkRobustShortCollector)
    assert isinstance(collectors[_SWEEP], LiquiditySweepLongCollector)
    assert isinstance(
        collectors[HYPE_COMPRESSION_ALIGNMENT_STRATEGY],
        HypeCompressionAlignmentCollector,
    )


def test_v52_builds_the_complete_runtime_poller() -> None:
    """Every v52 provider must have its source clock before live startup."""
    config = load_multi_asset_live_config(_PROFILE, mode="live")

    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda *_args, **_kwargs: None,
        backtest_lab_root=Path("../backtest-lab/backtest_lab"),
    )

    assert isinstance(poller, ConfiguredMultiAssetIntentPoller)


def test_v52_hype_opposite_signal_closes_without_same_cycle_reversal() -> None:
    """An aligned opposite HYPE signal must close before any later re-entry."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == HYPE_COMPRESSION_ALIGNMENT_STRATEGY
    )
    capability = StrategyCapability(
        provider.strategy_id,
        "HYPE",
        frozenset(provider.sides),
        provider.priority,
        provider.position_policy,
    )
    router = BidirectionalIntentRouter((capability,), maximum_positions=10)
    intent = StrategyIntent(
        provider.strategy_id,
        "HYPE",
        "long",
        1_786_700_000_000,
        56.0,
        "confirmed_aligned_opposite_signal",
    )

    report = router.route((intent,), positions={"HYPE": PositionState("HYPE", "short")})

    assert [(action.action, action.side) for action in report.actions] == [
        ("close", "long")
    ]
    assert report.withheld == ()


def test_v52_stress_is_bound_to_actual_two_asset_roster() -> None:
    """Unused account capacity cannot be presented as current route exposure."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    report = json.loads(_STRESS.read_text(encoding="utf-8"))
    scenario = report["scenario"]

    assert report["profile_id"] == config.profile_id
    assert report["profile_fingerprint"] == config.profile_fingerprint
    assert scenario["configured_assets"] == 2
    assert scenario["actual_position_count"] == 2
    assert scenario["actual_roster_maximum_margin_fraction"] == pytest.approx(0.20)
    assert scenario["actual_p99_stop_wave_loss_usd"] == pytest.approx(92.847534)
    assert scenario["actual_p99_stop_wave_loss_pct_equity"] == pytest.approx(1.856951)
