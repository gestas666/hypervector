"""Causal path conditions for optional completed-bar signal exits."""

from __future__ import annotations

import pandas as pd

from hypervector.research.shared_portfolio_models import (
    Direction,
    SharedPortfolioConfig,
)


def signal_exit_allowed(
    bars: pd.DataFrame,
    *,
    direction: Direction,
    entry_position: int,
    entry_price: float,
    current_position: int,
    config: SharedPortfolioConfig,
) -> bool:
    """Return whether an observed side exit satisfies configured path conditions."""
    maximum_age = config.signal_exit_max_age_bars
    maximum_mfe = config.signal_exit_max_mfe_bps
    minimum_adverse = config.signal_exit_min_adverse_bps
    if maximum_age is None and maximum_mfe is None and minimum_adverse is None:
        return True
    if maximum_age is None or maximum_mfe is None or minimum_adverse is None:
        raise ValueError("conditional signal-exit fields must be configured together")
    age = current_position - entry_position
    path = bars.iloc[entry_position : current_position + 1]
    favorable = _maximum_favorable_bps(path, direction, entry_price)
    current = _directional_return_bps(
        float(path["close"].iloc[-1]),
        direction,
        entry_price,
    )
    return (
        age <= maximum_age and favorable < maximum_mfe and current <= -minimum_adverse
    )


def _maximum_favorable_bps(
    path: pd.DataFrame,
    direction: Direction,
    entry_price: float,
) -> float:
    if direction == "long":
        favorable_price = float(path["high"].max())
        return 10_000.0 * (favorable_price - entry_price) / entry_price
    favorable_price = float(path["low"].min())
    return 10_000.0 * (entry_price - favorable_price) / entry_price


def _directional_return_bps(
    close: float,
    direction: Direction,
    entry_price: float,
) -> float:
    sign = 1.0 if direction == "long" else -1.0
    return sign * 10_000.0 * (close - entry_price) / entry_price
