"""Finite visible-depth market-order fill calculations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
import math

MarketSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class DepthLevel:
    """One visible price level with aggregate base-asset quantity."""

    price: float
    size: float

    def __post_init__(self) -> None:
        """Reject unusable or success-shaped depth observations."""
        _positive_finite(self.price, "price")
        _positive_finite(self.size, "size")


@dataclass(frozen=True)
class MarketDepthFill:
    """VWAP and visible-depth sufficiency for one marketable order."""

    side: MarketSide
    requested_quantity: float
    filled_quantity: float
    unfilled_quantity: float
    vwap: float
    best_price: float
    worst_price: float
    impact_bps: float
    levels_consumed: int
    complete: bool


def depth_levels_from_records(
    value: object,
    *,
    label: str,
) -> tuple[DepthLevel, ...]:
    """Convert database L2 records into validated visible depth levels."""
    if not isinstance(value, list) or not value:
        raise ValueError(f"book {label} must be a non-empty list")
    levels: list[DepthLevel] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError(f"book {label} must contain level objects")
        price, size = raw.get("px"), raw.get("sz")
        if isinstance(price, bool) or not isinstance(price, (float, int)):
            raise ValueError(f"book {label} level px must be numeric")
        if isinstance(size, bool) or not isinstance(size, (float, int)):
            raise ValueError(f"book {label} level sz must be numeric")
        levels.append(DepthLevel(float(price), float(size)))
    return tuple(levels)


def walk_market_order(
    levels: Sequence[DepthLevel],
    *,
    side: MarketSide,
    quantity: float,
) -> MarketDepthFill:
    """Consume finite asks for a buy or bids for a sell without extrapolation."""
    _validate_request(levels, side, quantity)
    remaining = quantity
    filled = 0.0
    quote = 0.0
    worst = levels[0].price
    consumed = 0
    for level in levels:
        take = min(remaining, level.size)
        if take <= 0.0:
            break
        filled += take
        quote += take * level.price
        remaining -= take
        worst = level.price
        consumed += 1
        if remaining <= _quantity_tolerance(quantity):
            remaining = 0.0
            break
    vwap = quote / filled
    best = levels[0].price
    return MarketDepthFill(
        side=side,
        requested_quantity=quantity,
        filled_quantity=filled,
        unfilled_quantity=max(remaining, 0.0),
        vwap=vwap,
        best_price=best,
        worst_price=worst,
        impact_bps=_impact_bps(side, best, vwap),
        levels_consumed=consumed,
        complete=remaining == 0.0,
    )


def _validate_request(
    levels: Sequence[DepthLevel],
    side: object,
    quantity: float,
) -> None:
    if side not in ("buy", "sell"):
        raise ValueError("side must be buy or sell")
    _positive_finite(quantity, "quantity")
    if not levels:
        raise ValueError("levels must contain visible depth")
    prices = [level.price for level in levels]
    if side == "buy" and any(left >= right for left, right in zip(prices, prices[1:])):
        raise ValueError("buy levels must be strictly ascending")
    if side == "sell" and any(left <= right for left, right in zip(prices, prices[1:])):
        raise ValueError("sell levels must be strictly descending")


def _impact_bps(side: MarketSide, best: float, vwap: float) -> float:
    if side == "buy":
        return (vwap / best - 1.0) * 10_000.0
    return (1.0 - vwap / best) * 10_000.0


def _quantity_tolerance(quantity: float) -> float:
    return max(quantity * 1e-12, 1e-12)


def _positive_finite(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
