"""Validated restart operations shared by the event shadow port."""

from __future__ import annotations

import math

from hypervector.data.hl_events import L2SnapshotEvent
from hypervector.execution import OrderCommand
from hypervector.paper.shadow_execution_models import ShadowOrder, timestamp_ms


class ShadowRestoreMixin:
    """Restore durable account and open-order state without claiming fills."""

    _symbol: str
    _initial_cash: float
    _realized_equity: float
    _orders: dict[str, ShadowOrder]
    _evidence_fresh: bool
    _position_quantity: float
    _position_average_price: float | None
    _position_fees: float
    _funding_net: float
    _last_mark: float | None
    _last_observed_at: str
    _latest_book: L2SnapshotEvent | None
    _max_event_age_ms: int

    def restore_position(
        self,
        *,
        quantity: float,
        average_price: float,
        realized_pnl: float,
        fees_paid_usd: float,
        funding_net_usd: float,
        observed_at: str,
    ) -> None:
        """Restore validated isolated account state without creating a fill."""
        values = (
            quantity,
            average_price,
            realized_pnl,
            fees_paid_usd,
            funding_net_usd,
        )
        if not all(isinstance(value, (int, float)) for value in values):
            raise TypeError("restored account values must be numeric")
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("restored account values must be finite")
        if quantity != 0.0 and average_price <= 0.0:
            raise ValueError("restored open position requires positive average price")
        if fees_paid_usd < 0.0:
            raise ValueError("restored fees must be non-negative")
        timestamp_ms(observed_at)
        self._position_quantity = float(quantity)
        self._position_average_price = float(average_price) if quantity != 0.0 else None
        self._position_fees = float(fees_paid_usd)
        self._funding_net = float(funding_net_usd)
        self._realized_equity = self._initial_cash + float(realized_pnl)
        self._last_mark = self._position_average_price
        self._last_observed_at = observed_at

    def restore_order(self, command: OrderCommand, *, cumulative: float) -> None:
        """Requeue one durable open order pending fresh post-restart evidence."""
        if command.symbol != self._symbol:
            raise ValueError(f"command symbol {command.symbol!r} != {self._symbol!r}")
        if command.client_order_id in self._orders:
            raise ValueError(f"duplicate client_order_id {command.client_order_id!r}")
        if not math.isfinite(cumulative) or not 0.0 <= cumulative < command.quantity:
            raise ValueError(
                "restored cumulative quantity must be within [0, quantity)"
            )
        self._orders[command.client_order_id] = ShadowOrder(
            command=command,
            activation_ms=timestamp_ms(command.submitted_at),
            cumulative_quantity=float(cumulative),
        )

    @property
    def evidence_fresh(self) -> bool:
        """Return whether matching has continuous fresh public evidence."""
        return self._evidence_fresh

    def evidence_fresh_at(self, observed_at: str) -> bool:
        """Return whether the latest complete book is fresh at a decision time."""
        book = self._latest_book
        if not self._evidence_fresh or book is None:
            return False
        age_ms = timestamp_ms(observed_at) - book.exchange_ts_ms
        return 0 <= age_ms <= self._max_event_age_ms
