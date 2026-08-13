"""Isolated liquidation and adverse-price helpers for low-TF replay."""

from __future__ import annotations

from hypervector.nautilus.hyperliquid_margin import (
    IsolatedMarginPosition,
    maintenance_rate_for_max_leverage,
)
from hypervector.research.shared_portfolio_models import Direction


def low_tf_liquidation_price(
    *,
    symbol: str,
    direction: Direction,
    quantity: float,
    entry_price: float,
    isolated_margin: float,
    entry_fee: float,
    funding_cashflow: float,
    venue_max_leverage: float,
) -> float:
    """Return the current funding-aware isolated liquidation boundary."""
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


def adverse_low_tf_price(
    price: float,
    direction: Direction,
    slippage_bps_per_side: float,
    *,
    entering: bool,
) -> float:
    """Apply declared residual slippage in the adverse direction."""
    higher = (direction == "long") == entering
    offset = slippage_bps_per_side / 10_000.0
    return price * (1.0 + offset if higher else 1.0 - offset)


def low_tf_stop_is_adverse(direction: Direction, stop: float, entry: float) -> bool:
    """Return whether the stop anchor remains beyond the filled entry."""
    return stop < entry if direction == "long" else stop > entry


def low_tf_target_is_favorable(
    direction: Direction, target: float, entry: float
) -> bool:
    """Return whether the target remains favorable after entry slippage."""
    return target > entry if direction == "long" else target < entry
