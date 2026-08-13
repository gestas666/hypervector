"""Causal live-provider contracts for the qualified HIP-3 roster."""

from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.hip3_cohort_providers import (
    HIP3_BREAKOUT_COMMODITY_STRATEGY,
    HIP3_BREAKOUT_COMMODITY_FRESH15_STRATEGY,
    HIP3_BREAKOUT_INDEX_STRATEGY,
    HIP3_BREAKOUT_INDEX_FRESH15_STRATEGY,
    HIP3_SWING_COMMODITY_STRATEGY,
    HIP3_SWING_INDEX_STRATEGY,
    Hip3BreakoutPressureCollector,
    Hip3LedgerPressureSource,
    Hip3PressureObservation,
    Hip3SwingHaCollector,
    configured_hip3_collector,
)
from hypervector.live.hip3_provider_recipes import configured_hip3_recipe
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.swing_ha_signals import SwingHaSignalConfig


def _bars(periods: int = 12) -> pd.DataFrame:
    timestamps = pd.date_range("2026-08-07T12:00:00Z", periods=periods, freq="15min")
    closes = [100.0 + position for position in range(periods)]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": [value + 1.0 for value in closes],
            "low": [value - 1.0 for value in closes],
            "close": closes,
            "volume": [10.0] * periods,
        }
    )


def _swing_signals(bars: pd.DataFrame, config: SwingHaSignalConfig) -> pd.DataFrame:
    output = pd.DataFrame(index=bars.index)
    output["long_entry"] = False
    output.loc[output.index[-1], "long_entry"] = True
    output["short_entry"] = False
    output["buy_state"] = True
    output["sell_state"] = False
    output["ha_color"] = 1
    output["ema_fast"] = 110.0
    output["ema_slow"] = 100.0
    output["active_ob_direction"] = 1
    output["last_pivot_high"] = 105.0
    output["last_pivot_low"] = 95.0
    return output


def _decimal_swing_signals(
    bars: pd.DataFrame,
    config: SwingHaSignalConfig,
) -> pd.DataFrame:
    output = _swing_signals(bars, config)
    output["ha_color"] = [Decimal("1")] * len(output)
    output["active_ob_direction"] = [Decimal("1")] * len(output)
    return output


def _swing_long_exit_signals(
    bars: pd.DataFrame,
    config: SwingHaSignalConfig,
) -> pd.DataFrame:
    output = _swing_signals(bars, config)
    output["long_entry"] = False
    output["long_exit"] = False
    output.loc[output.index[-1], "long_exit"] = True
    output["short_exit"] = False
    output["gap_recovery_exit"] = False
    output.loc[output.index[-1], "ha_color"] = -1
    return output


def _swing_gap_exit_signals(
    bars: pd.DataFrame,
    config: SwingHaSignalConfig,
) -> pd.DataFrame:
    output = _swing_long_exit_signals(bars, config)
    output.loc[output.index[-1], "short_exit"] = True
    output.loc[output.index[-1], "gap_recovery_exit"] = True
    return output


def _breakout_signals(
    bars: pd.DataFrame,
    config: Hip3BreakoutPressureConfig,
) -> pd.DataFrame:
    output = pd.DataFrame(index=bars.index)
    output["long_entry"] = False
    output.loc[output.index[-1], "long_entry"] = True
    output["short_entry"] = False
    output["prior_breakout_high"] = 108.0
    output["prior_breakout_low"] = 98.0
    output["fast_ema"] = 110.0
    output["slow_ema"] = 100.0
    output["decision_imbalance_10"] = bars["decision_imbalance_10"]
    return output


class _PressureSource:
    def __init__(self, value: Hip3PressureObservation | None) -> None:
        self._value = value

    def latest_at_or_before(
        self,
        symbol: str,
        not_after_ms: int,
    ) -> Hip3PressureObservation | None:
        return self._value


def test_swing_collector_emits_exact_namespaced_long_intent() -> None:
    """A completed BUY plus green alignment becomes one attributed intent."""
    observed = pd.Timestamp("2026-08-07T15:00:01Z")
    collector = Hip3SwingHaCollector(
        strategy_id=HIP3_SWING_INDEX_STRATEGY,
        config=SwingHaSignalConfig(fast_ema=2, slow_ema=3, pivot_length=1),
        signal_builder=_swing_signals,
    )

    batch = collector(
        _bars(),
        symbol="xyz:SP500",
        observed_at=observed,
        after_decision_time_ms=int(
            pd.Timestamp("2026-08-07T14:45:00Z").timestamp() * 1_000
        ),
    )

    assert len(batch.intents) == 1
    assert batch.intents[0].symbol == "xyz:SP500"
    assert batch.intents[0].side == "long"
    assert batch.evaluations[0].eligible is True
    assert batch.evaluations[0].readiness.conditions_met == 5


def test_swing_collector_preserves_numpy_integer_readiness_metrics() -> None:
    """Valid aligned numeric states must not render as unavailable telemetry."""
    collector = Hip3SwingHaCollector(
        strategy_id=HIP3_SWING_INDEX_STRATEGY,
        config=SwingHaSignalConfig(fast_ema=2, slow_ema=3, pivot_length=1),
        signal_builder=_swing_signals,
    )

    batch = collector(
        _bars(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-07T15:00:01Z"),
        after_decision_time_ms=int(
            pd.Timestamp("2026-08-07T14:45:00Z").timestamp() * 1_000
        ),
    )

    readiness = batch.evaluations[0].readiness
    assert readiness.metrics["ha_color"] == 1.0
    assert readiness.metrics["active_order_block_direction"] == 1.0
    assert "HA COLOR 1" in readiness.indicators
    assert "ORDER BLOCK 1" in readiness.indicators


def test_swing_collector_preserves_decimal_readiness_metrics() -> None:
    """DuckDB decimal states used for execution must remain visible telemetry."""
    collector = Hip3SwingHaCollector(
        strategy_id=HIP3_SWING_COMMODITY_STRATEGY,
        config=SwingHaSignalConfig(
            fast_ema=2,
            slow_ema=3,
            pivot_length=1,
            entry_mode="onset",
            order_block_role="agreement",
        ),
        signal_builder=_decimal_swing_signals,
    )

    batch = collector(
        _bars(),
        symbol="xyz:GOLD",
        observed_at=pd.Timestamp("2026-08-07T15:00:01Z"),
        after_decision_time_ms=int(
            pd.Timestamp("2026-08-07T14:45:00Z").timestamp() * 1_000
        ),
    )

    readiness = batch.evaluations[0].readiness
    assert batch.evaluations[0].eligible is True
    assert readiness.metrics["ha_color"] == 1.0
    assert readiness.metrics["active_order_block_direction"] == 1.0
    assert "HA COLOR 1" in readiness.indicators
    assert "ORDER BLOCK 1" in readiness.indicators


def test_swing_collector_exposes_ha_flip_exit_without_entry_intent() -> None:
    """A completed HA reversal must remain an attributed live exit fact."""
    collector = Hip3SwingHaCollector(
        strategy_id=HIP3_SWING_COMMODITY_STRATEGY,
        config=SwingHaSignalConfig(
            fast_ema=2,
            slow_ema=3,
            pivot_length=1,
            entry_mode="onset",
            exit_mode="ha_flip",
        ),
        signal_builder=_swing_long_exit_signals,
    )

    batch = collector(
        _bars(),
        symbol="xyz:GOLD",
        observed_at=pd.Timestamp("2026-08-07T15:00:01Z"),
        after_decision_time_ms=int(
            pd.Timestamp("2026-08-07T14:45:00Z").timestamp() * 1_000
        ),
    )

    evaluation = batch.evaluations[0]
    assert batch.intents == ()
    assert evaluation.eligible is False
    assert evaluation.exit_sides == frozenset({"long"})
    assert evaluation.exit_reason == "hip3_swing_ha_flip"
    assert evaluation.decision_action == "close_long"
    assert evaluation.as_payload()["exit_sides"] == ["long"]


def test_swing_collector_exposes_gap_recovery_for_either_open_side() -> None:
    """An archive recovery boundary must close either bound direction."""
    collector = Hip3SwingHaCollector(
        strategy_id=HIP3_SWING_INDEX_STRATEGY,
        config=SwingHaSignalConfig(
            fast_ema=2,
            slow_ema=3,
            pivot_length=1,
            exit_mode="alignment_loss",
        ),
        signal_builder=_swing_gap_exit_signals,
    )

    batch = collector(
        _bars(),
        symbol="xyz:SP500",
        observed_at=pd.Timestamp("2026-08-07T15:00:01Z"),
        after_decision_time_ms=int(
            pd.Timestamp("2026-08-07T14:45:00Z").timestamp() * 1_000
        ),
    )

    evaluation = batch.evaluations[0]
    assert evaluation.exit_sides == frozenset({"long", "short"})
    assert evaluation.exit_reason == "hip3_swing_gap_recovery"
    assert evaluation.decision_action == "close_open_position"


def test_breakout_collector_requires_fresh_depth_ten_pressure() -> None:
    """Price/EMA breakout alone cannot masquerade as order-flow confirmation."""
    observed = pd.Timestamp("2026-08-07T15:00:05Z")
    decision_ms = int(pd.Timestamp("2026-08-07T15:00:00Z").timestamp() * 1_000)
    config = Hip3BreakoutPressureConfig(3, 2, 3, 0.2, 80.0)
    boundary = int(pd.Timestamp("2026-08-07T14:45:00Z").timestamp() * 1_000)
    available = Hip3BreakoutPressureCollector(
        strategy_id=HIP3_BREAKOUT_INDEX_STRATEGY,
        config=config,
        pressure_source=_PressureSource(
            Hip3PressureObservation(
                recv_ts_ms=decision_ms - 1_000,
                imbalance_10=0.6,
            )
        ),
        signal_builder=_breakout_signals,
    )
    unavailable = Hip3BreakoutPressureCollector(
        strategy_id=HIP3_BREAKOUT_INDEX_STRATEGY,
        config=config,
        pressure_source=_PressureSource(None),
        signal_builder=_breakout_signals,
    )

    accepted = available(
        _bars(),
        symbol="xyz:SP500",
        observed_at=observed,
        after_decision_time_ms=boundary,
    )
    blocked = unavailable(
        _bars(),
        symbol="xyz:SP500",
        observed_at=observed,
        after_decision_time_ms=boundary,
    )

    assert len(accepted.intents) == 1
    assert accepted.evaluations[0].readiness.metrics["imbalance_10"] == 0.6
    assert blocked.intents == ()
    assert "order_pressure_unavailable" in blocked.evaluations[0].readiness.blockers


def test_default_breakout_collector_uses_observed_pressure_freshness(
    tmp_path: Path,
) -> None:
    """The production builder must consume measured live freshness without defaults."""
    observed = pd.Timestamp("2026-08-07T15:00:05Z")
    decision_ms = int(pd.Timestamp("2026-08-07T15:00:00Z").timestamp() * 1_000)
    asset = tmp_path / "xyz:sp500.jsonl"
    payload = {
        "event_type": "book_observation",
        "payload": {
            "source": "hyperliquid_mainnet_l2_rest",
            "recv_ts_ms": decision_ms - 1_000,
            "bids": [{"size": 3.0}] * 10,
            "asks": [{"size": 1.0}] * 10,
        },
    }
    asset.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    bars = _bars()
    bars.loc[bars.index[-1], ["open", "high", "low", "close"]] = [
        114.0,
        116.0,
        113.0,
        115.0,
    ]
    collector = Hip3BreakoutPressureCollector(
        strategy_id=HIP3_BREAKOUT_INDEX_STRATEGY,
        config=Hip3BreakoutPressureConfig(3, 2, 3, 0.2, 80.0),
        pressure_source=Hip3LedgerPressureSource(
            asset_ledgers={"xyz:SP500": asset},
            cohort_ledger=tmp_path / "cohort.jsonl",
        ),
    )

    batch = collector(
        bars,
        symbol="xyz:SP500",
        observed_at=observed,
        after_decision_time_ms=int(
            pd.Timestamp("2026-08-07T14:45:00Z").timestamp() * 1_000
        ),
    )

    assert len(batch.intents) == 1
    assert batch.evaluations[0].eligible is True
    assert batch.evaluations[0].readiness.metrics["imbalance_10"] == 0.5


@pytest.mark.parametrize("offset_ms", (-31_000, 1_000))
def test_breakout_collector_rejects_stale_or_future_pressure(
    offset_ms: int,
) -> None:
    """Cutoff selection cannot weaken the existing temporal safety boundary."""
    observed = pd.Timestamp("2026-08-07T15:00:05Z")
    decision_ms = int(pd.Timestamp("2026-08-07T15:00:00Z").timestamp() * 1_000)
    collector = Hip3BreakoutPressureCollector(
        strategy_id=HIP3_BREAKOUT_INDEX_STRATEGY,
        config=Hip3BreakoutPressureConfig(3, 2, 3, 0.2, 80.0),
        pressure_source=_PressureSource(
            Hip3PressureObservation(
                recv_ts_ms=decision_ms + offset_ms,
                imbalance_10=0.6,
            )
        ),
        signal_builder=_breakout_signals,
    )

    batch = collector(
        _bars(),
        symbol="xyz:SP500",
        observed_at=observed,
        after_decision_time_ms=int(
            pd.Timestamp("2026-08-07T14:45:00Z").timestamp() * 1_000
        ),
    )

    assert batch.intents == ()
    assert "order_pressure_unavailable" in batch.evaluations[0].readiness.blockers


def test_configured_collectors_use_frozen_research_parameters(tmp_path: Path) -> None:
    """Each staged strategy identity resolves to its journaled frozen recipe."""
    ledgers = {"xyz:SP500": tmp_path / "xyz:sp500.jsonl"}

    swing = configured_hip3_collector(
        HIP3_SWING_INDEX_STRATEGY,
        asset_ledgers=ledgers,
        cohort_ledger=tmp_path / "decisions.jsonl",
    )
    breakout = configured_hip3_collector(
        HIP3_BREAKOUT_INDEX_STRATEGY,
        asset_ledgers=ledgers,
        cohort_ledger=tmp_path / "decisions.jsonl",
    )

    assert isinstance(swing, Hip3SwingHaCollector)
    assert swing.config == SwingHaSignalConfig(
        fast_ema=50,
        slow_ema=200,
        pivot_length=8,
        entry_mode="state",
        exit_mode="alignment_loss",
        order_block_role="agreement",
        order_block_periods=5,
        order_block_minimum_move_pct=0.5,
    )
    assert isinstance(breakout, Hip3BreakoutPressureCollector)
    assert breakout.config == Hip3BreakoutPressureConfig(32, 21, 55, 0.1, 120.0)
    assert isinstance(breakout.pressure_source, Hip3LedgerPressureSource)


@pytest.mark.parametrize(
    ("strategy_id", "expected"),
    (
        (
            HIP3_SWING_INDEX_STRATEGY,
            SwingHaSignalConfig(
                fast_ema=50,
                slow_ema=200,
                pivot_length=8,
                entry_mode="state",
                exit_mode="alignment_loss",
                order_block_role="agreement",
                order_block_periods=5,
                order_block_minimum_move_pct=0.5,
            ),
        ),
        (
            HIP3_SWING_COMMODITY_STRATEGY,
            SwingHaSignalConfig(
                fast_ema=50,
                slow_ema=200,
                pivot_length=8,
                entry_mode="onset",
                exit_mode="ha_flip",
                order_block_role="agreement",
                order_block_periods=3,
                order_block_minimum_move_pct=0.5,
            ),
        ),
        (
            HIP3_BREAKOUT_INDEX_STRATEGY,
            Hip3BreakoutPressureConfig(32, 21, 55, 0.1, 120.0),
        ),
        (
            HIP3_BREAKOUT_INDEX_FRESH15_STRATEGY,
            Hip3BreakoutPressureConfig(32, 21, 55, 0.1, 120.0),
        ),
        (
            HIP3_BREAKOUT_COMMODITY_STRATEGY,
            Hip3BreakoutPressureConfig(32, 21, 55, 0.35, 120.0),
        ),
        (
            HIP3_BREAKOUT_COMMODITY_FRESH15_STRATEGY,
            Hip3BreakoutPressureConfig(32, 21, 55, 0.35, 120.0),
        ),
    ),
)
def test_configured_recipe_accessor_is_the_live_collector_source(
    tmp_path: Path,
    strategy_id: str,
    expected: SwingHaSignalConfig | Hip3BreakoutPressureConfig,
) -> None:
    recipe = configured_hip3_recipe(strategy_id)
    collector = configured_hip3_collector(
        strategy_id,
        asset_ledgers={"xyz:SP500": tmp_path / "asset.jsonl"},
        cohort_ledger=tmp_path / "cohort.jsonl",
    )

    assert recipe == expected
    assert collector.config == recipe
