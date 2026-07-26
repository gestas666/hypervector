"""Venue-neutral exact tick rounding for execution commands."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR


def round_price_to_tick(
    price: float,
    *,
    tick_size: float,
    upward: bool,
) -> float:
    """Round a price outward to an exact venue tick."""
    tick = Decimal(str(tick_size))
    if tick <= 0:
        raise ValueError("tick_size must be positive")
    rounding = ROUND_CEILING if upward else ROUND_FLOOR
    units = (Decimal(str(price)) / tick).to_integral_value(rounding=rounding)
    return float(units * tick)
