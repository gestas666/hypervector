"""Reusable side and largest-winner attribution for shared portfolio reports."""

from __future__ import annotations

from collections import Counter

from hypervector.research.shared_portfolio_models import SharedPortfolioTrade


def trade_attribution(
    trades: tuple[SharedPortfolioTrade, ...],
) -> dict[str, object]:
    """Attribute one account's completed trades by side and exit reason."""
    reasons = Counter(trade.exit_reason for trade in trades)
    return {
        "long": _direction_attribution(trades, "long"),
        "short": _direction_attribution(trades, "short"),
        "exit_reasons": dict(sorted(reasons.items())),
    }


def _direction_attribution(
    trades: tuple[SharedPortfolioTrade, ...],
    direction: str,
) -> dict[str, int | float | None]:
    selected = tuple(trade for trade in trades if trade.direction == direction)
    profits = tuple(trade.net_pnl_usd for trade in selected if trade.net_pnl_usd > 0.0)
    losses = tuple(-trade.net_pnl_usd for trade in selected if trade.net_pnl_usd <= 0.0)
    gross_profit = sum(profits)
    gross_loss = sum(losses)
    net_pnl = sum(trade.net_pnl_usd for trade in selected)
    largest_winner = max(profits) if profits else None
    return {
        "completed_trades": len(selected),
        "wins": len(profits),
        "losses": len(losses),
        "net_pnl_usd": net_pnl,
        "gross_profit_usd": gross_profit,
        "gross_loss_usd": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0.0 else None,
        "largest_winner_usd": largest_winner,
        "largest_winner_share_of_gross_profit_pct": (
            100.0 * largest_winner / gross_profit
            if largest_winner is not None
            else None
        ),
        "net_pnl_excluding_largest_winner_usd": (
            net_pnl - largest_winner if largest_winner is not None else net_pnl
        ),
        "fees_usd": sum(trade.fees_usd for trade in selected),
        "funding_cashflow_usd": sum(trade.funding_cashflow_usd for trade in selected),
    }
