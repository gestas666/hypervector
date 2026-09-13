"""Offline exact-fill economics; allocation is not a venue margin/liquidation model."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, localcontext
from types import MappingProxyType
from typing import Mapping

from hypervector.research.native_replay_events import (
    FillEvent,
    FundingEvent,
    Stamp,
    require_amount,
    require_clock,
    require_name,
)

REPLAY_DECIMAL_PRECISION = 50
ZERO = Decimal(0)


@dataclass(frozen=True)
class ReplayPosition:
    """One asset's average-cost exposure, preserving its first decision origin."""

    symbol: str
    opening_order_id: str
    quantity_signed: Decimal
    entry_notional_usd: Decimal
    leverage: Decimal
    decision_time_ms: int
    first_fill_time_ms: int

    @property
    def entry_price(self) -> Decimal:
        """Return average entry cost at the declared replay decimal precision."""
        with localcontext() as context:
            context.prec = REPLAY_DECIMAL_PRECISION
            return self.entry_notional_usd / abs(self.quantity_signed)

    @property
    def allocated_initial_margin_usd(self) -> Decimal:
        """Report entry-cost allocation, without claiming venue withdrawability."""
        with localcontext() as context:
            context.prec = REPLAY_DECIMAL_PRECISION
            return self.entry_notional_usd / self.leverage


@dataclass(frozen=True)
class AccountView:
    """Immutable shared economic totals and their last mutation observation."""

    stamp: Stamp | None
    cash_usd: Decimal
    realized_gross_usd: Decimal
    fees_usd: Decimal
    funding_usd: Decimal
    unrealized_pnl_usd: Decimal
    equity_usd: Decimal
    gross_notional_usd: Decimal
    allocated_initial_margin_usd: Decimal
    positions: Mapping[str, ReplayPosition]
    mark_prices: Mapping[str, Decimal]


class ExactFillAccount:
    """Apply observed exact fills atomically without re-sizing or profitability gates."""

    def __init__(self, initial_cash_usd: Decimal, symbols: tuple[str, ...]) -> None:
        """Start a flat declared universe; market marks must arrive explicitly."""
        require_amount(initial_cash_usd, "initial cash", positive=True)
        if not isinstance(symbols, tuple) or not symbols or len(set(symbols)) != len(symbols):
            raise ValueError("configured symbols must be a nonempty unique tuple")
        for symbol in symbols:
            require_name(symbol, "configured symbol")
        self._symbols = frozenset(symbols)
        self._cash = initial_cash_usd
        self._realized = self._fees = self._funding = ZERO
        self._stamp: Stamp | None = None
        self._positions: dict[str, ReplayPosition] = {}
        self._marks: dict[str, tuple[int, Decimal]] = {}
        self._fills: dict[str, FillEvent] = {}
        self._settlements: dict[str, FundingEvent] = {}

    def mark(
        self,
        stamp: Stamp,
        *,
        source_time_ms: int,
        prices: Mapping[str, Decimal],
    ) -> None:
        """Commit a valid causal mark publication without partial symbol updates."""
        self._require_order(stamp)
        require_clock(source_time_ms, "mark source time")
        if source_time_ms > stamp.observed_time_ms or not prices:
            raise ValueError("mark source must be available and prices nonempty")
        updates: dict[str, tuple[int, Decimal]] = {}
        for symbol, price in prices.items():
            self._require_symbol(symbol)
            require_amount(price, "mark price", positive=True)
            previous = self._marks.get(symbol)
            if previous is not None and source_time_ms < previous[0]:
                raise ValueError("mark source time must not move backwards")
            if previous is not None and source_time_ms == previous[0] and price != previous[1]:
                raise ValueError("conflicting mark price at the same source time")
            updates[symbol] = (source_time_ms, price)
        self._marks.update(updates)
        self._stamp = stamp

    def apply_fill(self, event: FillEvent) -> bool:
        """Apply one new fill, preserving submitted quantity and economic identity."""
        prior = self._fills.get(event.fill_id)
        if prior is not None:
            if replace(event, stamp=prior.stamp) != prior:
                raise ValueError("conflicting fill identity")
            return False
        self._require_order(event.stamp)
        self._require_symbol(event.symbol)
        if event.symbol not in self._marks:
            raise ValueError("fill requires an explicit available mark for its symbol")
        old = self._positions.get(event.symbol)
        with localcontext() as context:
            context.prec = REPLAY_DECIMAL_PRECISION
            position, gross = _reduce(old, event) if event.reduce_only else _open(old, event)
            cash = self._cash + gross - event.fee_usd
            realized, fees = self._realized + gross, self._fees + event.fee_usd
        if position is None:
            del self._positions[event.symbol]
        else:
            self._positions[event.symbol] = position
        self._cash, self._realized, self._fees = cash, realized, fees
        self._fills[event.fill_id] = event
        self._stamp = event.stamp
        return True

    def apply_funding(self, event: FundingEvent) -> bool:
        """Apply signed settlement cash once even when its position has closed."""
        prior = self._settlements.get(event.event_id)
        if prior is not None:
            if replace(event, stamp=prior.stamp) != prior:
                raise ValueError("conflicting funding identity")
            return False
        self._require_order(event.stamp)
        self._require_symbol(event.symbol)
        with localcontext() as context:
            context.prec = REPLAY_DECIMAL_PRECISION
            cash, funding = self._cash + event.amount_usd, self._funding + event.amount_usd
        self._cash, self._funding = cash, funding
        self._settlements[event.event_id] = event
        self._stamp = event.stamp
        return True

    def snapshot(self) -> AccountView:
        """Return a stable economic view without fabricating absent price evidence."""
        with localcontext() as context:
            context.prec = REPLAY_DECIMAL_PRECISION
            unrealized = gross = margin = ZERO
            for symbol, position in self._positions.items():
                quantity = position.quantity_signed
                mark = self._marks[symbol][1]
                direction = Decimal(1) if quantity > 0 else Decimal(-1)
                unrealized += mark * quantity - direction * position.entry_notional_usd
                gross += abs(quantity) * mark
                margin += position.allocated_initial_margin_usd
            return AccountView(
                self._stamp,
                self._cash,
                self._realized,
                self._fees,
                self._funding,
                unrealized,
                self._cash + unrealized,
                gross,
                margin,
                MappingProxyType(dict(self._positions)),
                MappingProxyType({symbol: mark[1] for symbol, mark in self._marks.items()}),
            )

    def _require_order(self, stamp: Stamp) -> None:
        if not isinstance(stamp, Stamp):
            raise ValueError("mutation requires an observation Stamp")
        if self._stamp is not None and stamp <= self._stamp:
            raise ValueError("observation order must strictly increase")

    def _require_symbol(self, symbol: str) -> None:
        if symbol not in self._symbols:
            raise ValueError(f"symbol is not configured: {symbol}")


def _open(old: ReplayPosition | None, event: FillEvent) -> tuple[ReplayPosition, Decimal]:
    quantity = event.quantity if event.side == "buy" else -event.quantity
    notional = event.quantity * event.price
    if old is None:
        return ReplayPosition(
            event.symbol,
            event.order_id,
            quantity,
            notional,
            event.leverage,
            event.decision_time_ms,
            event.fill_time_ms,
        ), ZERO
    if old.quantity_signed * quantity < 0:
        raise ValueError("opening fill cannot reverse an existing position")
    if (
        old.opening_order_id != event.order_id
        or old.leverage != event.leverage
        or old.decision_time_ms != event.decision_time_ms
    ):
        raise ValueError("partial opening fill must retain its order, leverage and decision")
    return replace(
        old,
        quantity_signed=old.quantity_signed + quantity,
        entry_notional_usd=old.entry_notional_usd + notional,
        first_fill_time_ms=min(old.first_fill_time_ms, event.fill_time_ms),
    ), ZERO


def _reduce(
    old: ReplayPosition | None,
    event: FillEvent,
) -> tuple[ReplayPosition | None, Decimal]:
    if old is None:
        raise ValueError("reduction requires an open position")
    if (old.quantity_signed > 0) == (event.side == "buy"):
        raise ValueError("reduction side must be opposite the open position")
    if event.quantity > abs(old.quantity_signed):
        raise ValueError("reduction quantity exceeds open exposure")
    if event.leverage != old.leverage:
        raise ValueError("reduction leverage differs from open position")
    fraction = event.quantity / abs(old.quantity_signed)
    removed_cost = old.entry_notional_usd * fraction
    direction = Decimal(1) if old.quantity_signed > 0 else Decimal(-1)
    gross = direction * (event.price * event.quantity - removed_cost)
    remaining = old.quantity_signed - direction * event.quantity
    if remaining == 0:
        return None, gross
    return replace(
        old, quantity_signed=remaining, entry_notional_usd=old.entry_notional_usd - removed_cost
    ), gross
