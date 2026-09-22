"""Same-entry followthrough counterfactual with next-open fills and actual funding."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.research.failed_followthrough import failed_followthrough
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioTrade,
)
from hypervector.research.shared_portfolio_pricing import adverse_price


@dataclass(frozen=True)
class FailureReplay:
    """Matched path outcome; does not simulate additional trades after early exits."""

    original_net_usd: float
    counterfactual_net_usd: float
    exit_position: int
    changed: bool


def replay_failed_followthrough(
    bars: pd.DataFrame,
    trade: SharedPortfolioTrade,
    config: SharedPortfolioConfig,
) -> FailureReplay:
    """Preserve original native exits, applying only earlier causally observed failures."""
    if trade.stop_price is None:
        raise ValueError("failure replay requires the entry's bound native stop")
    risk = abs(trade.stop_price / trade.entry_price - 1) * 10_000
    sign = 1 if trade.direction == "long" else -1
    peak = 0.0
    for position in range(trade.entry_position, trade.exit_position - 1):
        current = (
            sign * (float(bars.close.iloc[position]) / trade.entry_price - 1) * 10_000
        )
        peak = max(peak, current)
        age = (
            bars.index[position + 1] - bars.index[trade.entry_position]
        ).total_seconds()
        if failed_followthrough(
            age_seconds=age,
            current_bps=current,
            peak_close_bps=peak,
            initial_stop_bps=risk,
        ):
            return _outcome(bars, trade, config, position + 1)
    return FailureReplay(
        trade.net_pnl_usd, trade.net_pnl_usd, trade.exit_position, False
    )


def _outcome(
    bars: pd.DataFrame,
    trade: SharedPortfolioTrade,
    config: SharedPortfolioConfig,
    position: int,
) -> FailureReplay:
    sign = 1 if trade.direction == "long" else -1
    exit_price = adverse_price(
        float(bars.open.iloc[position]),
        trade.direction,
        entering=False,
        slippage_bps=config.market_exit_slippage_bps,
    )
    gross = sign * trade.quantity * (exit_price - trade.entry_price)
    fees = (
        trade.notional_usd * config.entry_fee_rate
        + trade.quantity * exit_price * config.market_exit_fee_rate
    )
    held = bars.iloc[trade.entry_position + 1 : position + 1]
    funding = (
        -sign * trade.quantity * float((held.open * held[config.funding_column]).sum())
    )
    return FailureReplay(trade.net_pnl_usd, gross - fees + funding, position, True)
