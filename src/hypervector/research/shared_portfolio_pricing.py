"""Generic price and timer arithmetic for shared portfolio research."""

from __future__ import annotations

from hypervector.research.shared_portfolio_models import Direction


def adverse_price(
    price: float,
    direction: Direction,
    slippage_bps: float,
    *,
    entering: bool,
) -> float:
    """Apply adverse slippage for the side and lifecycle operation."""
    fraction = slippage_bps / 10_000.0
    higher = (direction == "long") == entering
    return price * (1.0 + fraction if higher else 1.0 - fraction)


def adverse_barrier_or_open(
    direction: Direction,
    barrier: float,
    bar_open: float,
) -> float:
    """Prevent a stop or liquidation from improving through a price gap."""
    return min(barrier, bar_open) if direction == "long" else max(barrier, bar_open)


def margin_barrier(
    entry: float,
    direction: Direction,
    margin_pct: float | None,
    leverage: float,
    *,
    favorable: bool,
) -> float | None:
    """Convert a return-on-margin threshold into an absolute price barrier."""
    if margin_pct is None:
        return None
    fraction = margin_pct / 100.0 / leverage
    positive = (direction == "long") == favorable
    return entry * (1.0 + fraction if positive else 1.0 - fraction)


def maximum_hold_reached(
    entry_position: int,
    position: int,
    maximum_hold_bars: int | None,
) -> bool:
    """Return whether the inclusive bar-count lifecycle ceiling is reached."""
    return maximum_hold_bars is not None and (
        position - entry_position + 1 >= maximum_hold_bars
    )
