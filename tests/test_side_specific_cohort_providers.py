"""Aggregate bidirectional coverage for side-specialist cohort providers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.btc_hulk_robust_short_provider import HulkRobustShortCollector
from hypervector.live.btc_liquidity_sweep_readiness import (
    liquidity_sweep_long_readiness,
)
from hypervector.live.btc_liquidity_sweep_long_provider import (
    LiquiditySweepLongCollector,
)
from hypervector.live.hulk_smash_live_decisions import HulkSmashLiveDecision
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError
from hypervector.live.multi_asset_polling_contract import (
    READINESS_SEED_LOOKBACK_MINUTES,
    SOURCE_TIMEFRAMES,
)

_BASE = Path("configs/multi_asset_bidirectional_focused_growth_5000_candidate_v42.toml")
_HULK_BLOCK = """[[providers]]
strategy_id = "hulk_expansion_bidirectional_tuned_v2"
symbols = ["BTC"]
sides = ["long", "short"]
priority = 10
timeframe = "30m"
maximum_entry_delay_seconds = 60
execution_symbols = ["BTC"]
execution = { entry_liquidity = "taker_ioc", stop_policy = "structural_clamped_bps", minimum_stop_bps = 20.0, maximum_stop_bps = 75.0, target_policy = "reward_risk", target_r_multiple = 3.0, maximum_hold_seconds = 86400 }
"""
_SPECIALIST_BLOCKS = """[[providers]]
strategy_id = "hulk_expansion_short_robust_v3"
symbols = ["BTC"]
sides = ["short"]
priority = 20
timeframe = "30m"
maximum_entry_delay_seconds = 60
execution_symbols = ["BTC"]
execution = { entry_liquidity = "taker_ioc", stop_policy = "structural_clamped_bps", minimum_stop_bps = 20.0, maximum_stop_bps = 75.0, target_policy = "reward_risk", target_r_multiple = 3.0, maximum_hold_seconds = 86400 }

[[providers]]
strategy_id = "liquidity_sweep_long_1h_stop60_v1"
symbols = ["BTC"]
sides = ["long"]
priority = 10
timeframe = "1h"
maximum_entry_delay_seconds = 60
execution_symbols = ["BTC"]
execution = { entry_liquidity = "taker_ioc", stop_policy = "fixed_bps", stop_bps = 60.0, target_policy = "fixed_bps", target_bps = 26.666666666666668, maximum_hold_seconds = 86400 }
"""


def test_side_specialists_may_jointly_supply_btc_bidirectional_coverage(
    tmp_path: Path,
) -> None:
    """The asset stays bidirectional while each strategy keeps honest scope."""
    text = _BASE.read_text(encoding="utf-8").replace(
        _HULK_BLOCK,
        _SPECIALIST_BLOCKS,
    )
    profile = tmp_path / "side-specialists.toml"
    profile.write_text(text, encoding="utf-8")

    config = load_multi_asset_live_config(profile, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}

    assert providers["hulk_expansion_short_robust_v3"].sides == {"short"}
    assert providers["liquidity_sweep_long_1h_stop60_v1"].sides == {"long"}
    assert (
        "hulk_expansion_short_robust_v3",
        "BTC",
        "short",
    ) in config.executable_provider_directions
    assert (
        "liquidity_sweep_long_1h_stop60_v1",
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


def test_default_collector_builds_the_frozen_robust_short_provider(
    tmp_path: Path,
) -> None:
    """The shared poller can instantiate the forward-tested short identity."""
    text = _BASE.read_text(encoding="utf-8").replace(
        _HULK_BLOCK,
        _SPECIALIST_BLOCKS,
    )
    profile = tmp_path / "short-collector.toml"
    profile.write_text(text, encoding="utf-8")
    config = load_multi_asset_live_config(profile, mode="observe")
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == "hulk_expansion_short_robust_v3"
    )

    collector = build_default_collector(provider, config, tmp_path)

    assert type(collector).__name__ == "HulkRobustShortCollector"


def test_default_collector_builds_the_liquidity_sweep_long_provider(
    tmp_path: Path,
) -> None:
    """The shared poller instantiates the distinct forward-tested long arm."""
    text = _BASE.read_text(encoding="utf-8").replace(
        _HULK_BLOCK,
        _SPECIALIST_BLOCKS,
    )
    profile = tmp_path / "long-collector.toml"
    profile.write_text(text, encoding="utf-8")
    config = load_multi_asset_live_config(profile, mode="observe")
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == "liquidity_sweep_long_1h_stop60_v1"
    )

    collector = build_default_collector(provider, config, tmp_path)

    assert type(collector).__name__ == "LiquiditySweepLongCollector"


def test_robust_short_collector_emits_only_the_frozen_short_identity(
    tmp_path: Path,
) -> None:
    """The robust provider cannot inherit the rejected bidirectional profile."""
    observed = pd.Timestamp("2026-08-11T17:00:00Z")
    decision = HulkSmashLiveDecision(
        decision_time_ms=int(observed.timestamp() * 1_000),
        bar_open_at=observed - pd.Timedelta(minutes=30),
        reference_price=64_000.0,
        open_price=64_100.0,
        high_price=64_200.0,
        low_price=63_900.0,
        volume=100.0,
        candidate="hulk_rebuilt_expansion_v1",
        score=7,
        minimum_score=7,
        trigger="squeeze_release",
        evidence=("squeeze_release", "adx_usable"),
        stop_anchor=64_200.0,
        entry_eligible=True,
        reason="eligible",
        signal_side="short",
    )
    observed_args: dict[str, object] = {}

    def build(*args: object, **kwargs: object) -> tuple[HulkSmashLiveDecision, ...]:
        observed_args.update(kwargs)
        return (decision,)

    collector = HulkRobustShortCollector(
        backtest_lab_root=tmp_path,
        decision_builder=build,
    )

    batch = collector(
        pd.DataFrame(),
        symbol="BTC",
        observed_at=observed,
        after_decision_time_ms=None,
    )

    assert observed_args["allowed_sides"] == frozenset({"short"})
    assert [(intent.strategy_id, intent.side) for intent in batch.intents] == [
        ("hulk_expansion_short_robust_v3", "short")
    ]
    assert batch.evaluations[0].strategy_id == "hulk_expansion_short_robust_v3"
    assert batch.latest_decision_time_ms == decision.decision_time_ms


def test_liquidity_sweep_long_uses_only_completed_hourly_decisions() -> None:
    """The long provider emits at the hour close with exact BTC attribution."""
    times = pd.date_range("2026-08-09T06:00:00Z", periods=56 * 60, freq="1min")
    bars = pd.DataFrame(
        {
            "timestamp": times,
            "open": 100.0,
            "high": 100.5,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0 / 60.0,
        }
    )
    final_hour = bars.index[-60:]
    bars.loc[final_hour, "volume"] = 2.0 / 60.0
    bars.loc[final_hour[0], "low"] = 98.0
    bars.loc[final_hour[-1], "close"] = 100.25
    decisions = pd.DataFrame(
        {"entry_direction": ["long"], "structural_direction": ["long"]},
        index=pd.DatetimeIndex([times[-1]]),
    )
    collector = LiquiditySweepLongCollector(
        decision_builder=lambda _: decisions,
    )

    batch = collector(
        bars,
        symbol="BTC",
        observed_at=times[-1] + pd.Timedelta(minutes=1),
        after_decision_time_ms=None,
    )

    decision_ms = int((times[-1] + pd.Timedelta(minutes=1)).timestamp() * 1_000)
    assert [(intent.strategy_id, intent.side) for intent in batch.intents] == [
        ("liquidity_sweep_long_1h_stop60_v1", "long")
    ]
    assert batch.intents[0].decision_time_ms == decision_ms
    assert batch.intents[0].reference_price == 100.25
    assert batch.latest_decision_time_ms == decision_ms
    assert batch.evaluations[0].eligible is True
    assert batch.evaluations[0].readiness.conditions_met == 4
    assert batch.evaluations[0].readiness.blockers == ()


def test_robust_short_uses_five_minute_source_and_completed_thirty_minute_seed() -> (
    None
):
    """Polling preserves the standalone provider's causal source-clock contract."""
    assert SOURCE_TIMEFRAMES["hulk_expansion_short_robust_v3"] == "5m"
    assert READINESS_SEED_LOOKBACK_MINUTES["hulk_expansion_short_robust_v3"] == 31


def test_liquidity_sweep_uses_minute_source_and_completed_hourly_seed() -> None:
    """The sweep builder receives minute bars and seeds one completed hour."""
    strategy = "liquidity_sweep_long_1h_stop60_v1"

    assert SOURCE_TIMEFRAMES[strategy] == "1m"
    assert READINESS_SEED_LOOKBACK_MINUTES[strategy] == 61


def test_liquidity_sweep_readiness_exposes_all_four_entry_components() -> None:
    """The cockpit shows the exact sweep, reclaim, volume, and EMA state."""
    index = pd.date_range("2026-08-01T00:00:00Z", periods=56, freq="1h")
    bars = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.5,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
        },
        index=index,
    )
    bars.loc[index[-1], ["low", "close", "volume"]] = [98.0, 100.25, 2.0]

    readiness = liquidity_sweep_long_readiness(bars, index[-1])

    assert readiness.conditions_met == 4
    assert readiness.conditions_required == 4
    assert readiness.blockers == ()
    assert readiness.metrics["prior_20h_low"] == 99.0
    assert readiness.metrics["volume_multiple"] == 2.0
    assert readiness.metrics["clearance_bps"] > 100.0
    assert readiness.metrics["close_above_ema55"] is True
    assert "SWEEP" in readiness.indicators[0]


def test_liquidity_sweep_readiness_names_the_missing_volume_condition() -> None:
    """A near-trigger remains observable without becoming an entry gate change."""
    index = pd.date_range("2026-08-01T00:00:00Z", periods=56, freq="1h")
    bars = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.5,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
        },
        index=index,
    )
    bars.loc[index[-1], ["low", "close"]] = [98.0, 100.25]

    readiness = liquidity_sweep_long_readiness(bars, index[-1])

    assert readiness.conditions_met == 3
    assert readiness.blockers == ("volume_below_1.20x",)
