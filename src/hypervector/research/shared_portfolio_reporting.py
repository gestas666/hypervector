"""Aggregate reporting for one chronological shared trade stream."""

from __future__ import annotations

from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
    SharedPortfolioTrade,
)


def build_shared_portfolio_report(
    *,
    equity: float,
    maximum_drawdown_pct: float,
    conflicts: int,
    barrier_invalidated_entries: int,
    gap_expired_entries: int,
    maximum_concurrent_positions: int,
    trades: list[SharedPortfolioTrade],
    config: SharedPortfolioConfig,
) -> SharedPortfolioReport:
    """Aggregate portfolio and monthly metrics without double funding."""
    profits = [trade.net_pnl_usd for trade in trades if trade.net_pnl_usd > 0.0]
    losses = [-trade.net_pnl_usd for trade in trades if trade.net_pnl_usd <= 0.0]
    gross_profit, gross_loss = sum(profits), sum(losses)
    return SharedPortfolioReport(
        config.initial_equity,
        equity,
        equity - config.initial_equity,
        100.0 * (equity - config.initial_equity) / config.initial_equity,
        maximum_drawdown_pct,
        len(trades),
        len(profits),
        len(losses),
        gross_profit,
        gross_loss,
        gross_profit / gross_loss if gross_loss else None,
        sum(trade.exit_reason == "liquidation" for trade in trades),
        sum(trade.fees_usd for trade in trades),
        sum(trade.funding_cashflow_usd for trade in trades),
        conflicts,
        maximum_concurrent_positions,
        sum(trade.exit_reason == "end_of_data" for trade in trades),
        barrier_invalidated_entries,
        equity <= 0.0,
        _monthly_pnl(trades),
        _limitations(config),
        tuple(trades),
        gap_expired_entries,
    )


def _monthly_pnl(trades: list[SharedPortfolioTrade]) -> dict[str, float]:
    result: dict[str, float] = {}
    for trade in trades:
        month = trade.exit_time_utc[:7]
        result[month] = result.get(month, 0.0) + trade.net_pnl_usd
    return result


def _limitations(config: SharedPortfolioConfig) -> tuple[str, ...]:
    return (
        "bar screening only; no queue position or depth-constrained fill probability",
        "same-bar paths use liquidation, then stop, then target ordering",
        "intrabar barrier exit times use the first observed bar quote as a proxy",
        f"funding uses {config.funding_column} at supplied rows and bar-open mark proxy",
        "promotion requires venue event replay with mark, funding, trades, and L2 depth",
    )
