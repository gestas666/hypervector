"""Hyperliquid-style market liquidation mechanics for shadow positions."""

from __future__ import annotations

from dataclasses import dataclass

from hypervector.data.hl_events import L2SnapshotEvent
from hypervector.execution import VenueOrderEvent
from hypervector.nautilus.hyperliquid_margin import (
    IsolatedMarginPosition,
    IsolatedMarginState,
)
from hypervector.paper.liquidation_execution import (
    BACKSTOP_MAINTENANCE_FRACTION,
    LIQUIDATION_COOLDOWN_MS,
    LIQUIDATION_EXECUTION_MODEL,
    PARTIAL_LIQUIDATION_FRACTION,
    PARTIAL_LIQUIDATION_THRESHOLD_USD,
)
from hypervector.paper.shadow_execution_models import (
    ShadowLiquidation,
    ShadowOrder,
    positive,
    state_event,
    timestamp_ms,
)


@dataclass(frozen=True)
class LiquidationBookFill:
    """One market-order walk through currently displayed public depth."""

    requested_quantity: float
    filled_quantity: float
    average_price: float | None


@dataclass(frozen=True)
class _LiquidationOutcome:
    fee_usd: float
    remaining_quantity: float
    execution_price: float
    backstop_quantity: float


def walk_liquidation_book(
    *,
    position_quantity: float,
    requested_quantity: float,
    book: L2SnapshotEvent,
) -> LiquidationBookFill:
    """Walk bids for a long liquidation and asks for a short liquidation."""
    levels = book.bids if position_quantity > 0.0 else book.asks
    remaining = requested_quantity
    notional = 0.0
    filled = 0.0
    for level in levels:
        consumed = min(remaining, level.size)
        notional += consumed * level.price
        filled += consumed
        remaining -= consumed
        if remaining <= 1e-12:
            break
    average = notional / filled if filled > 0.0 else None
    return LiquidationBookFill(requested_quantity, filled, average)


class ShadowLiquidationMixin:
    """Apply partial/full liquidation attempts using fresh displayed L2."""

    _symbol: str
    _taker_fee_rate: float
    _orders: dict[str, ShadowOrder]
    _events: list[VenueOrderEvent]
    _latest_book: L2SnapshotEvent | None
    _position_quantity: float
    _position_average_price: float | None
    _position_fees: float
    _realized_equity: float
    _last_mark: float | None
    _last_observed_at: str
    _last_liquidation: ShadowLiquidation | None
    _liquidation_cooldown_until_ms: int | None

    def _scale_open_cost_basis(
        self,
        *,
        before_quantity: float,
        remaining_quantity: float,
    ) -> None: ...

    def mark(self, *, mark_price: float, observed_at: str) -> bool:
        """Apply a mark and execute a supported isolated liquidation attempt."""
        positive(mark_price, "mark_price")
        observed_ms = timestamp_ms(observed_at)
        self._last_mark = mark_price
        self._last_observed_at = observed_at
        position = self._margin_position()
        if position is None:
            return False
        state = position.state(mark_price)
        if not state.liquidatable:
            return False
        if not self.evidence_fresh_at(observed_at) or self._latest_book is None:
            self._annotate_uncertain()
            return False
        requested, partial_rule = self._liquidation_quantity(mark_price, observed_ms)
        fill = walk_liquidation_book(
            position_quantity=self._position_quantity,
            requested_quantity=requested,
            book=self._latest_book,
        )
        if fill.filled_quantity <= 0.0 and not self._requires_backstop(mark_price):
            self._annotate_uncertain()
            return False
        if partial_rule and fill.filled_quantity > 0.0:
            self._liquidation_cooldown_until_ms = observed_ms + LIQUIDATION_COOLDOWN_MS
        self._apply_liquidation_fill(
            position=position,
            state=state,
            fill=fill,
            mark_price=mark_price,
            observed_at=observed_at,
            partial_rule=partial_rule,
        )
        return True

    def _liquidation_quantity(
        self,
        mark_price: float,
        observed_ms: int,
    ) -> tuple[float, bool]:
        quantity = abs(self._position_quantity)
        in_cooldown = (
            self._liquidation_cooldown_until_ms is not None
            and observed_ms < self._liquidation_cooldown_until_ms
        )
        partial = quantity * mark_price > PARTIAL_LIQUIDATION_THRESHOLD_USD
        partial = partial and not in_cooldown
        if not partial:
            return quantity, False
        return quantity * PARTIAL_LIQUIDATION_FRACTION, True

    def _apply_liquidation_fill(
        self,
        *,
        position: IsolatedMarginPosition,
        state: IsolatedMarginState,
        fill: LiquidationBookFill,
        mark_price: float,
        observed_at: str,
        partial_rule: bool,
    ) -> None:
        before = self._position_quantity
        outcome = self._apply_execution(fill=fill, mark_price=mark_price)
        self._last_liquidation = ShadowLiquidation(
            symbol=self._symbol,
            observed_at=observed_at,
            mark_price=mark_price,
            boundary_price=position.liquidation_price(),
            position_quantity=before,
            isolated_margin_usd=position.isolated_margin,
            position_equity_usd=state.equity_usd,
            maintenance_margin_usd=state.maintenance_margin_usd,
            execution_fee_usd=outcome.fee_usd,
            clearance_fee_usd=0.0,
            execution_model=LIQUIDATION_EXECUTION_MODEL,
            method="backstop" if outcome.backstop_quantity > 0.0 else "market",
            attempted_quantity=fill.requested_quantity,
            filled_quantity=fill.filled_quantity + outcome.backstop_quantity,
            remaining_quantity=outcome.remaining_quantity,
            execution_price=outcome.execution_price,
            partial_rule_applied=partial_rule,
            cooldown_until_ms=self._liquidation_cooldown_until_ms,
            market_filled_quantity=fill.filled_quantity,
            backstop_quantity=outcome.backstop_quantity,
        )
        self._cancel_liquidated_orders(observed_at)
        if outcome.remaining_quantity <= 1e-12:
            self._clear_position()

    def _apply_execution(
        self,
        *,
        fill: LiquidationBookFill,
        mark_price: float,
    ) -> _LiquidationOutcome:
        entry = self._position_average_price
        price = fill.average_price
        if entry is None:
            raise RuntimeError("liquidation position state is incomplete")
        before = self._position_quantity
        side = 1.0 if before > 0.0 else -1.0
        market_pnl = (
            side * fill.filled_quantity * (price - entry) if price is not None else 0.0
        )
        fee = fill.filled_quantity * (price or 0.0) * self._taker_fee_rate
        self._realized_equity += market_pnl - fee
        remaining = max(0.0, abs(before) - fill.filled_quantity)
        self._position_quantity = side * remaining
        if remaining > 1e-12:
            self._scale_open_cost_basis(
                before_quantity=abs(before),
                remaining_quantity=remaining,
            )
        backstop = (
            remaining > 1e-12
            and fill.filled_quantity < fill.requested_quantity
            and self._requires_backstop(mark_price)
        )
        backstop_quantity = 0.0
        execution_price = price or entry
        if backstop:
            backstop_quantity = remaining
            transferred_margin = self.position_margin_usd
            self._realized_equity -= transferred_margin
            total_pnl = market_pnl - transferred_margin
            execution_price = entry + total_pnl / (side * abs(before))
            remaining = 0.0
            self._position_quantity = 0.0
        return _LiquidationOutcome(
            fee_usd=fee,
            remaining_quantity=remaining,
            execution_price=execution_price,
            backstop_quantity=backstop_quantity,
        )

    def _requires_backstop(self, mark_price: float) -> bool:
        position = self._margin_position()
        if position is None:
            return False
        state = position.state(mark_price)
        return (
            state.equity_usd
            < state.maintenance_margin_usd * BACKSTOP_MAINTENANCE_FRACTION
        )

    def _cancel_liquidated_orders(self, observed_at: str) -> None:
        for order in self._orders.values():
            if order.status == "terminal":
                continue
            order.status = "terminal"
            self._events.append(
                state_event(
                    order.command.client_order_id,
                    "canceled",
                    observed_at,
                    reason="isolated_liquidation",
                    cumulative=order.cumulative_quantity,
                )
            )
