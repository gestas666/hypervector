"""Bounded transfer protocol for HIP-3 breakout-pressure challengers."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.hip3_breakout_pressure_transfer import (
    quote_aware_portfolio_config,
    run_hip3_breakout_pressure_transfer,
)
from hypervector.research.hip3_swing_transfer import (
    Hip3ExecutionFriction,
    Hip3TransferAsset,
)


def _asset() -> Hip3TransferAsset:
    pattern = [
        100.0,
        100.0,
        100.0,
        101.0,
        102.0,
        103.0,
        102.0,
        101.0,
        100.0,
        99.0,
        98.0,
        97.0,
        98.0,
        99.0,
    ]
    closes = (pattern * 12)[:160]
    index = pd.date_range("2026-01-01", periods=len(closes), freq="15min", tz="UTC")
    changes = pd.Series(closes, index=index).diff().fillna(0.0)
    bars = pd.DataFrame(
        {
            "open": closes,
            "high": [value + 0.1 for value in closes],
            "low": [value - 0.1 for value in closes],
            "close": closes,
            "entry_bid": [value - 0.01 for value in closes],
            "entry_ask": [value + 0.01 for value in closes],
            "decision_bid": [value - 0.01 for value in closes],
            "decision_ask": [value + 0.01 for value in closes],
            "decision_imbalance_10": changes.map(
                lambda value: 0.5 if value > 0.0 else -0.5 if value < 0.0 else 0.0
            ),
            "gap_before_bars": [0] * len(closes),
            "end_boundary_age_ms": [100] * len(closes),
            "source_snapshot_count": [100] * len(closes),
            "funding_rate": [0.0] * len(closes),
        },
        index=index,
    )
    return Hip3TransferAsset("xyz:TEST", 10.0, bars)


def _friction() -> Hip3ExecutionFriction:
    return Hip3ExecutionFriction(75.0, 0.00001, 1.0, 0.5, 4.0, 2.0)


def _config(threshold: float) -> Hip3BreakoutPressureConfig:
    return Hip3BreakoutPressureConfig(3, 2, 3, threshold, 80.0)


def test_selects_only_on_development_and_keeps_holdout_sealed() -> None:
    result = run_hip3_breakout_pressure_transfer(
        (_asset(),),
        {"xyz:TEST": _friction()},
        configs=(_config(0.2), _config(0.9)),
    )

    assert len(result.trials) == 2
    assert result.selected_config == _config(0.2)
    assert result.trials[0].completed_fold_trades > 0
    assert result.holdout_status == "sealed_not_evaluated"
    assert result.execution_authority == "none"
    assert len(result.validation_nominal) == 1
    assert len(result.validation_stress) == 1


def test_quote_aware_friction_uses_observed_sides_and_tail_stress_delta() -> None:
    nominal = quote_aware_portfolio_config(_asset(), _friction(), stress=False)
    stress = quote_aware_portfolio_config(_asset(), _friction(), stress=True)

    assert nominal.open_bid_column == "entry_bid"
    assert nominal.open_ask_column == "entry_ask"
    assert nominal.close_bid_column == "decision_bid"
    assert nominal.close_ask_column == "decision_ask"
    assert nominal.entry_slippage_bps == 0.5
    assert stress.entry_slippage_bps == 3.5
    assert nominal.margin_fraction == 0.03
    assert nominal.entry_fee_rate == 0.00001
