"""Acceptance contract for the incremental tuned-v2 BTC short route."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hypervector.live.btc_hulk_robust_short_provider import (
    HULK_ROBUST_SHORT_STRATEGY,
    HULK_TUNED_SHORT_STRATEGY,
    HulkRobustShortCollector,
)
from hypervector.live.bidirectional_intents import (
    BidirectionalIntentRouter,
    PositionState,
    StrategyCapability,
    StrategyIntent,
)
from hypervector.live.hulk_smash_live_decisions import HulkSmashLiveDecision
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_polling_contract import (
    READINESS_SEED_LOOKBACK_MINUTES,
    SOURCE_TIMEFRAMES,
)
from hypervector.live.multi_asset_strategy_evidence import (
    strategy_research_evidence,
)
from hypervector.research.cohort_friction_contracts import modeled_contract

_V55 = Path("configs/multi_asset_growth_first_5000_spcx_cash_open_v55.toml")
_V56 = Path("configs/multi_asset_growth_first_5000_btc_tuned_v2_increment_v56.toml")


def _load(path: Path) -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(
        path,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )


def _eligible_short(observed: pd.Timestamp) -> HulkSmashLiveDecision:
    return HulkSmashLiveDecision(
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


def test_tuned_v2_collector_preserves_exact_strategy_identity(tmp_path: Path) -> None:
    """One injected v2 decision must not be mislabeled as robust v3."""
    observed = pd.Timestamp("2026-08-18T12:00:00Z")
    collector = HulkRobustShortCollector(
        backtest_lab_root=tmp_path,
        strategy_id=HULK_TUNED_SHORT_STRATEGY,
        decision_builder=lambda *args, **kwargs: (_eligible_short(observed),),
    )

    batch = collector(
        pd.DataFrame(),
        symbol="BTC",
        observed_at=observed,
        after_decision_time_ms=None,
    )

    assert [(row.strategy_id, row.side) for row in batch.intents] == [
        (HULK_TUNED_SHORT_STRATEGY, "short")
    ]
    assert batch.evaluations[0].strategy_id == HULK_TUNED_SHORT_STRATEGY


def test_v56_adds_v2_below_v3_without_changing_v55_contracts() -> None:
    """The successor adds one lower-priority route and preserves every v55 row."""
    v55 = _load(_V55)
    v56 = _load(_V56)
    providers = {row.strategy_id: row for row in v56.providers}

    old_assets = [
        (
            row.symbol,
            row.leverage,
            row.margin_fraction,
            row.max_notional_usd,
            row.stop_bps,
            row.maximum_hold_seconds,
        )
        for row in v55.assets
    ]
    new_assets = [
        (
            row.symbol,
            row.leverage,
            row.margin_fraction,
            row.max_notional_usd,
            row.stop_bps,
            row.maximum_hold_seconds,
        )
        for row in v56.assets
    ]
    assert new_assets == old_assets
    assert v56.providers[0] == v55.providers[0]
    assert v56.providers[2:] == v55.providers[1:]
    assert providers[HULK_TUNED_SHORT_STRATEGY].priority == 19
    assert providers[HULK_TUNED_SHORT_STRATEGY].execution == v55.providers[0].execution
    assert providers[HULK_TUNED_SHORT_STRATEGY].executable_sides("BTC") == {"short"}


def test_v2_collector_and_completed_bar_contract_are_registered(
    tmp_path: Path,
) -> None:
    """The default runtime can construct v2 from completed five-minute bars."""
    config = _load(_V56)
    provider = next(
        row for row in config.providers if row.strategy_id == HULK_TUNED_SHORT_STRATEGY
    )

    collector = build_default_collector(provider, config, tmp_path)

    assert isinstance(collector, HulkRobustShortCollector)
    assert SOURCE_TIMEFRAMES[HULK_TUNED_SHORT_STRATEGY] == "5m"
    assert READINESS_SEED_LOOKBACK_MINUTES[HULK_TUNED_SHORT_STRATEGY] == 31


def test_v2_tui_evidence_discloses_exact_btc_and_live_risk() -> None:
    """The cockpit must exclude SOL rows and include current live outcomes."""
    evidence = strategy_research_evidence(HULK_TUNED_SHORT_STRATEGY, "BTC")

    assert evidence.research_state == "exact_btc_partitions_mixed_live_probation"
    assert evidence.confidence == "low_to_medium"
    assert "59 exact BTC historical trades" in evidence.cadence
    assert "3 exact live closes" in evidence.cadence
    assert "SOL rows excluded" in evidence.summary
    assert "-$63.04" in evidence.summary
    assert "no established edge" in evidence.summary

    friction = modeled_contract(HULK_TUNED_SHORT_STRATEGY, "BTC")
    assert friction is not None
    assert friction.stop_policy == "structural_clamped_bps"
    assert friction.target_policy == "reward_risk"
    assert friction.maximum_hold_seconds == 86_400


def test_simultaneous_v2_v3_signal_keeps_robust_v3_priority() -> None:
    """The increment cannot displace v3 or create a second BTC position."""
    config = _load(_V56)
    capabilities = tuple(
        StrategyCapability(
            provider.strategy_id,
            symbol,
            provider.sides,
            provider.priority,
            provider.position_policy,
        )
        for provider in config.providers
        for symbol in provider.symbols
    )
    intents = tuple(
        StrategyIntent(strategy, "BTC", "short", 1_000, 60_000.0, "eligible")
        for strategy in (HULK_TUNED_SHORT_STRATEGY, HULK_ROBUST_SHORT_STRATEGY)
    )
    positions = {symbol: PositionState(symbol, None) for symbol in config.symbols}

    report = BidirectionalIntentRouter(
        capabilities,
        maximum_positions=config.maximum_positions,
    ).route(intents, positions=positions)

    assert [(row.strategy_id, row.action) for row in report.actions] == [
        (HULK_ROBUST_SHORT_STRATEGY, "enter")
    ]
    assert [(row.intent.strategy_id, row.reason) for row in report.withheld] == [
        (HULK_TUNED_SHORT_STRATEGY, "lower_provider_priority")
    ]
