"""Intrabar barrier and isolated-liquidation mechanics for research portfolios."""

from __future__ import annotations

from hypervector.nautilus.hyperliquid_margin import (
    IsolatedMarginPosition,
    maintenance_rate_for_max_leverage,
)
from hypervector.research.shared_portfolio_models import Direction, ExitReason
from hypervector.research.shared_portfolio_pricing import adverse_barrier_or_open


def barrier_hits(
    direction: Direction,
    high: float,
    low: float,
    liquidation: float,
    stop: float | None,
    target: float | None,
) -> dict[ExitReason, bool]:
    """Return all conservative intrabar risk and reward contacts."""
    if direction == "long":
        return {
            "liquidation": low <= liquidation,
            "stop": stop is not None and low <= stop,
            "target": target is not None and high >= target,
        }
    return {
        "liquidation": high >= liquidation,
        "stop": stop is not None and high >= stop,
        "target": target is not None and low <= target,
    }


def ordered_exit_reason(hits: dict[ExitReason, bool]) -> ExitReason | None:
    """Choose liquidation, then stop, then target for ambiguous bars."""
    for reason in ("liquidation", "stop", "target"):
        if hits[reason]:
            return reason
    return None


def barrier_exit_price(
    direction: Direction,
    liquidation: float,
    stop: float | None,
    target: float | None,
    reason: ExitReason,
    bar_open: float,
) -> float:
    """Return a barrier fill without improving through an opening gap."""
    if reason == "liquidation":
        return adverse_barrier_or_open(direction, liquidation, bar_open)
    if reason == "stop" and stop is not None:
        return adverse_barrier_or_open(direction, stop, bar_open)
    if reason == "target" and target is not None:
        return target
    raise RuntimeError(f"missing barrier price for {reason}")


def isolated_liquidation_price(
    symbol: str,
    direction: Direction,
    quantity: float,
    entry_price: float,
    isolated_margin: float,
    venue_max_leverage: float,
    entry_fee: float,
    funding_cashflow: float,
) -> float:
    """Return the Hyperliquid-compatible isolated liquidation boundary."""
    position = IsolatedMarginPosition(
        symbol=symbol,
        side=direction,
        quantity=quantity,
        entry_price=entry_price,
        isolated_margin=isolated_margin,
        maintenance_rate=maintenance_rate_for_max_leverage(venue_max_leverage),
        fees_paid_usd=entry_fee,
        funding_net_usd=funding_cashflow,
    )
    return position.liquidation_price()
