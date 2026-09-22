"""Causal matched-entry exit replay and counterexamples to early loss cutting."""

from dataclasses import replace

import pandas as pd
import pytest

from hypervector.research.completed_signal_projection import empty_directional_signals
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig
from hypervector.research.v92_failure_replay import replay_failed_followthrough


def _path(
    side: str = "long",
) -> tuple[pd.DataFrame, pd.DataFrame, SharedPortfolioConfig]:
    index = pd.date_range("2026-01-01", periods=8, freq="15min", tz="UTC")
    prices = pd.Series([100, 100, 98.8, 98.7, 99, 100, 101, 101.5], index=index)
    if side == "short":
        prices = 200 - prices
    bars = pd.DataFrame(
        {
            "open": prices,
            "high": prices + 0.1,
            "low": prices - 0.1,
            "close": prices,
            "funding_rate": 0.0001,
        },
        index=index,
    )
    signals = empty_directional_signals(
        index, signal_name="test", source_time_column="source"
    )
    signals.loc[index[0], ["entry_direction", f"{side}_entry", "stop_price"]] = [
        side,
        True,
        98 if side == "long" else 102,
    ]
    config = SharedPortfolioConfig(
        initial_equity=5000,
        margin_fraction=0.1,
        leverage=1,
        maximum_notional_usd=500,
        entry_slippage_bps=0,
        market_exit_slippage_bps=0,
        entry_fee_rate=0.0004,
        market_exit_fee_rate=0.0004,
    )
    return bars, signals, config


@pytest.mark.parametrize("side", ["long", "short"])
def test_failure_exit_is_next_open_and_reports_a_cut_winner(side: str) -> None:
    bars, signals, config = _path(side)
    trade = evaluate_shared_bar_portfolio(bars, signals, config).trades[0]
    result = replay_failed_followthrough(bars, trade, config)
    assert result.changed and result.exit_position == 3
    assert trade.net_pnl_usd > 0 and result.counterfactual_net_usd < 0
    sign = 1 if side == "long" else -1
    quantity = trade.quantity
    price = float(bars.open.iloc[3])
    expected = (
        sign * quantity * (price - 100) - 500 * 0.0004 - quantity * price * 0.0004
    )
    expected -= (
        sign
        * quantity
        * float((bars.open.iloc[2:4] * bars.funding_rate.iloc[2:4]).sum())
    )
    assert result.counterfactual_net_usd == pytest.approx(expected)


def test_native_stop_precedes_proposed_software_exit() -> None:
    bars, signals, config = _path()
    bars.loc[bars.index[2], "low"] = 97
    trade = evaluate_shared_bar_portfolio(bars, signals, config).trades[0]
    result = replay_failed_followthrough(bars, trade, config)
    assert trade.exit_reason == "stop" and not result.changed


def test_execution_cost_is_applied_at_early_exit() -> None:
    bars, signals, config = _path()
    config = replace(config, market_exit_slippage_bps=15)
    trade = evaluate_shared_bar_portfolio(bars, signals, config).trades[0]
    result = replay_failed_followthrough(bars, trade, config)
    baseline = replay_failed_followthrough(
        bars, trade, replace(config, market_exit_slippage_bps=0)
    )
    assert result.counterfactual_net_usd < baseline.counterfactual_net_usd


def test_gap_censoring_cannot_be_replaced_with_a_stale_software_fill() -> None:
    bars, signals, config = _path()
    bars["gap_before_bars"] = 0
    bars.loc[bars.index[3], "gap_before_bars"] = 1
    trade = evaluate_shared_bar_portfolio(bars, signals, config).trades[0]
    result = replay_failed_followthrough(bars, trade, config)
    assert trade.exit_reason == "data_gap"
    assert not result.changed
