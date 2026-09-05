"""Tests for shared HIP-3 development-only partition evaluation."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hip3_development_partitions import (
    evaluate_hip3_development_partitions,
)
from hypervector.research.mu_hip3_candidate import MuChronologicalWindows
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig


def _portfolio(stress: bool) -> SharedPortfolioConfig:
    """Return distinguishable nominal and stress execution inputs."""
    slippage = 2.0 if stress else 0.0
    return SharedPortfolioConfig(
        initial_equity=5000.0,
        margin_fraction=0.1,
        leverage=10.0,
        target_margin_pct=10.0,
        stop_margin_pct=5.0,
        entry_fee_rate=0.0,
        target_fee_rate=0.0,
        market_exit_fee_rate=0.0,
        liquidation_fee_rate=0.0,
        entry_slippage_bps=slippage,
        market_exit_slippage_bps=slippage,
    )


def test_development_partitions_are_half_open_and_withhold_oos() -> None:
    """Evaluate one development interval and its frozen folds only."""
    index = pd.date_range("2026-06-01", periods=12, freq="15min", tz="UTC")
    bars = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        index=index,
    )
    signals = pd.DataFrame(
        {
            "entry_direction": ["long"] + [None] * 11,
            "exit_signal": [False] * 12,
            "signal_name": ["fixture"] * 12,
        },
        index=index,
    )
    windows = MuChronologicalWindows(
        index[0],
        index[9],
        index[10],
        index[-1] + pd.Timedelta(minutes=15),
        ((index[0], index[3]), (index[3], index[6]), (index[6], index[9])),
    )

    development, folds = evaluate_hip3_development_partitions(
        bars, signals, windows, _portfolio
    )

    assert development.name == "development"
    assert development.start_utc == index[0]
    assert development.end_utc == index[9]
    assert [fold.name for fold in folds] == [
        "development_fold_1",
        "development_fold_2",
        "development_fold_3",
    ]
    exit_time = pd.Timestamp(development.nominal.trades[0].exit_time_utc)
    assert exit_time < index[9]
    assert (
        development.stress.trades[0].entry_price
        > development.nominal.trades[0].entry_price
    )
