"""Risk-budgeted sizing for causal shared portfolio research."""

from __future__ import annotations

from hypervector.research.shared_portfolio_models import (
    Direction,
    SharedPortfolioConfig,
)


def position_size(
    equity: float,
    entry: float,
    stop: float | None,
    direction: Direction,
    config: SharedPortfolioConfig,
) -> tuple[float, float]:
    """Return margin and notional after risk, margin, and dollar caps."""
    margin_cap_notional = equity * config.margin_fraction * config.leverage
    candidates = [margin_cap_notional]
    if config.maximum_notional_usd is not None:
        candidates.append(config.maximum_notional_usd)
    if config.risk_fraction_per_position is not None:
        stop_fraction = _adverse_stop_fraction(entry, stop, direction)
        candidates.append(equity * config.risk_fraction_per_position / stop_fraction)
    notional = min(candidates)
    return notional / config.leverage, notional


def _adverse_stop_fraction(
    entry: float,
    stop: float | None,
    direction: Direction,
) -> float:
    adverse = stop is not None and (
        stop < entry if direction == "long" else stop > entry
    )
    if not adverse:
        raise ValueError("risk_fraction_per_position requires a resolved adverse stop")
    return abs(entry - float(stop)) / entry
