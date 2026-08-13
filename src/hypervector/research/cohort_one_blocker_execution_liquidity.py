"""Liquidity-policy pricing for exact one-blocker execution replay."""

from __future__ import annotations

from hypervector.research.cohort_one_blocker_execution_contract import (
    OneBlockerExecutionContract,
)
from hypervector.research.cohort_one_blocker_execution_payloads import (
    entry_level,
    exit_level,
)
from hypervector.research.cohort_one_blocker_execution_types import Book
from hypervector.research.market_depth_fill import DepthLevel, walk_market_order


def entry_execution(
    book: Book,
    trade_direction: float,
    contract: OneBlockerExecutionContract,
) -> tuple[float, float]:
    """Return entry price and capacity under the explicit liquidity policy."""
    if contract.liquidity_policy == "top_level":
        return entry_level(book, trade_direction)
    levels = book.asks if trade_direction > 0.0 else book.bids
    return _walk_quote_notional(levels, contract.notional_usd)


def exit_execution(
    book: Book,
    trade_direction: float,
    position_size: float,
    contract: OneBlockerExecutionContract,
) -> tuple[float, float]:
    """Return exit price and capacity under the explicit liquidity policy."""
    if contract.liquidity_policy == "top_level":
        return exit_level(book, trade_direction)
    levels, side = (book.bids, "sell") if trade_direction > 0.0 else (book.asks, "buy")
    fill = walk_market_order(levels, side=side, quantity=position_size)
    return fill.vwap, fill.filled_quantity


def _walk_quote_notional(
    levels: tuple[DepthLevel, ...], notional_usd: float
) -> tuple[float, float]:
    remaining, filled, quote = notional_usd, 0.0, 0.0
    for level in levels:
        take = min(level.size, remaining / level.price)
        filled += take
        quote += take * level.price
        remaining -= take * level.price
        if remaining <= max(notional_usd * 1e-12, 1e-12):
            break
    return quote / filled, filled
