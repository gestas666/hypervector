"""Focused Hyperliquid isolated-margin and liquidation calculations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Mapping

PositionSide = Literal["long", "short"]
_LIQUIDATION_EPSILON_USD = 1e-9


@dataclass(frozen=True)
class IsolatedMarginState:
    """One position's mark-to-market maintenance state."""

    symbol: str
    mark_price: float
    notional_usd: float
    unrealized_pnl_usd: float
    equity_usd: float
    maintenance_margin_usd: float
    liquidatable: bool


@dataclass(frozen=True)
class IsolatedMarginPosition:
    """Inputs governing one independently collateralized linear perpetual."""

    symbol: str
    side: PositionSide
    quantity: float
    entry_price: float
    isolated_margin: float
    maintenance_rate: float
    maintenance_deduction: float = 0.0
    fees_paid_usd: float = 0.0
    funding_net_usd: float = 0.0

    def __post_init__(self) -> None:
        """Validate the isolated position and tier parameters."""
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if self.side not in {"long", "short"}:
            raise ValueError("side must be long|short")
        _positive(self.quantity, "quantity")
        _positive(self.entry_price, "entry_price")
        _positive(self.isolated_margin, "isolated_margin")
        _rate(self.maintenance_rate)
        _nonnegative(self.maintenance_deduction, "maintenance_deduction")
        _nonnegative(self.fees_paid_usd, "fees_paid_usd")
        _finite(self.funding_net_usd, "funding_net_usd")

    @property
    def effective_collateral_usd(self) -> float:
        """Return isolated collateral after fees and signed funding."""
        return self.isolated_margin - self.fees_paid_usd + self.funding_net_usd

    def maintenance_margin(self, mark_price: float) -> float:
        """Return tier-adjusted maintenance requirement at venue mark price."""
        _positive(mark_price, "mark_price")
        gross = self.quantity * mark_price * self.maintenance_rate
        return max(0.0, gross - self.maintenance_deduction)

    def state(self, mark_price: float) -> IsolatedMarginState:
        """Evaluate isolated equity and liquidation status at one mark."""
        _positive(mark_price, "mark_price")
        sign = 1.0 if self.side == "long" else -1.0
        unrealized = sign * self.quantity * (mark_price - self.entry_price)
        equity = self.effective_collateral_usd + unrealized
        maintenance = self.maintenance_margin(mark_price)
        return IsolatedMarginState(
            symbol=self.symbol,
            mark_price=mark_price,
            notional_usd=self.quantity * mark_price,
            unrealized_pnl_usd=unrealized,
            equity_usd=equity,
            maintenance_margin_usd=maintenance,
            liquidatable=equity <= maintenance + _LIQUIDATION_EPSILON_USD,
        )

    def liquidation_price(self) -> float:
        """Solve the official isolated maintenance boundary for mark price."""
        sign = 1.0 if self.side == "long" else -1.0
        numerator = (
            sign * self.quantity * self.entry_price
            - self.effective_collateral_usd
            - self.maintenance_deduction
        )
        denominator = self.quantity * (sign - self.maintenance_rate)
        price = numerator / denominator
        _positive(price, "liquidation_price")
        return price


@dataclass(frozen=True)
class IsolatedMarginEvaluation:
    """Portfolio view preserving each position's collateral boundary."""

    states: Mapping[str, IsolatedMarginState]
    liquidated_symbols: tuple[str, ...]
    surviving_margin_usd: float


@dataclass(frozen=True)
class IsolatedMarginPortfolio:
    """Collection of independent isolated positions; no collateral sharing."""

    positions: tuple[IsolatedMarginPosition, ...]

    def __post_init__(self) -> None:
        """Reject duplicate symbols that would make marks ambiguous."""
        symbols = [position.symbol for position in self.positions]
        if len(symbols) != len(set(symbols)):
            raise ValueError("isolated positions require unique symbols")

    def evaluate(self, marks: Mapping[str, float]) -> IsolatedMarginEvaluation:
        """Evaluate every position independently from the supplied venue marks."""
        missing = [
            position.symbol
            for position in self.positions
            if position.symbol not in marks
        ]
        if missing:
            raise ValueError(f"missing mark prices for {missing}")
        states = {
            position.symbol: position.state(float(marks[position.symbol]))
            for position in self.positions
        }
        liquidated = tuple(
            position.symbol
            for position in self.positions
            if states[position.symbol].liquidatable
        )
        surviving_margin = sum(
            position.isolated_margin
            for position in self.positions
            if not states[position.symbol].liquidatable
        )
        return IsolatedMarginEvaluation(
            states=states,
            liquidated_symbols=liquidated,
            surviving_margin_usd=surviving_margin,
        )


def maintenance_rate_for_max_leverage(max_leverage: float) -> float:
    """Return Hyperliquid maintenance rate: half max initial-margin rate."""
    _positive(max_leverage, "max_leverage")
    return 0.5 / max_leverage


def _rate(value: float) -> None:
    _positive(value, "maintenance_rate")
    if value >= 1.0:
        raise ValueError("maintenance_rate must be below 1.0")


def _positive(value: float, name: str) -> None:
    _finite(value, name)
    if value <= 0.0:
        raise ValueError(f"{name} must be positive")


def _nonnegative(value: float, name: str) -> None:
    _finite(value, name)
    if value < 0.0:
        raise ValueError(f"{name} must be non-negative")


def _finite(value: float, name: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
