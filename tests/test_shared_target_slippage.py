"""Taker target exits apply explicit adverse price movement and actual exit fees."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig


@pytest.mark.parametrize(
    "side,target,fill", [("long", 101.0, 100.9495), ("short", 99.0, 99.0495)]
)
def test_target_slippage_changes_fill_and_not_the_trigger(
    side: str,
    target: float,
    fill: float,
) -> None:
    """A crossed target retains its trigger but incurs the configured taker friction."""
    index = pd.date_range("2026-05-18", periods=3, freq="min", tz="UTC")
    bars = pd.DataFrame(
        {
            "open": 100.0,
            "high": [100.0, 102.0, 100.0],
            "low": [100.0, 98.0, 100.0],
            "close": 100.0,
        },
        index=index,
    )
    signals = pd.DataFrame(
        {"entry_direction": [side, None, None], "exit_signal": False}, index=index
    )
    config = SharedPortfolioConfig(
        initial_equity=1000.0,
        margin_fraction=0.05,
        leverage=2.0,
        target_margin_pct=2.0,
        entry_fee_rate=0.0,
        target_fee_rate=0.0004,
        entry_slippage_bps=0.0,
        target_slippage_bps=5.0,
    )
    result = evaluate_shared_bar_portfolio(bars, signals, config)
    (trade,) = result.trades
    assert trade.exit_reason == "target"
    assert trade.target_price == target
    assert trade.exit_price == pytest.approx(fill)
    assert trade.fees_usd == pytest.approx(fill * 0.0004)
    gross = 0.9495 if side == "long" else 0.9505
    assert trade.net_pnl_usd == pytest.approx(gross - fill * 0.0004)


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_invalid_target_slippage_fails_before_replay(value: float) -> None:
    """Invalid target friction cannot silently enter a research run."""
    with pytest.raises(ValueError, match="target_slippage_bps"):
        SharedPortfolioConfig(target_slippage_bps=value)
