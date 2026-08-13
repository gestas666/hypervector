"""Optional executable-quote boundaries for shared research portfolios."""

from __future__ import annotations

import math

import pandas as pd

from hypervector.research.shared_portfolio_models import (
    Direction,
    SharedPortfolioConfig,
)


def validate_execution_quotes(
    bars: pd.DataFrame,
    config: SharedPortfolioConfig,
) -> None:
    """Validate configured two-sided quote columns without midpoint fallbacks."""
    _validate_pair(bars, config.open_bid_column, config.open_ask_column)
    _validate_pair(bars, config.close_bid_column, config.close_ask_column)


def executable_open_price(
    bars: pd.DataFrame,
    position: int,
    direction: Direction,
    *,
    entering: bool,
    config: SharedPortfolioConfig,
) -> float:
    """Return the executable side at a bar's opening boundary."""
    if config.open_bid_column is None or config.open_ask_column is None:
        return float(bars["open"].iloc[position])
    use_ask = (direction == "long") == entering
    column = config.open_ask_column if use_ask else config.open_bid_column
    return float(bars[column].iloc[position])


def executable_close_price(
    bars: pd.DataFrame,
    position: int,
    direction: Direction,
    config: SharedPortfolioConfig,
) -> float:
    """Return the executable liquidation side at the terminal boundary."""
    if config.close_bid_column is None or config.close_ask_column is None:
        return float(bars["close"].iloc[position])
    column = config.close_bid_column if direction == "long" else config.close_ask_column
    return float(bars[column].iloc[position])


def _validate_pair(
    bars: pd.DataFrame,
    bid_column: str | None,
    ask_column: str | None,
) -> None:
    if bid_column is None or ask_column is None:
        return
    missing = {bid_column, ask_column}.difference(bars.columns)
    if missing:
        raise ValueError(f"shared portfolio quote columns missing: {sorted(missing)}")
    bid = pd.to_numeric(bars[bid_column], errors="raise")
    ask = pd.to_numeric(bars[ask_column], errors="raise")
    if (
        bid.isna().any()
        or ask.isna().any()
        or not bid.map(math.isfinite).all()
        or not ask.map(math.isfinite).all()
        or bid.le(0.0).any()
        or ask.le(0.0).any()
    ):
        raise ValueError(f"{bid_column}/{ask_column} must be finite and positive")
    if bid.gt(ask).any():
        raise ValueError(f"{bid_column}/{ask_column} contains crossed quotes")
