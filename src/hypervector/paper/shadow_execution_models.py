"""Typed evidence models and constructors for event-driven shadow execution."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Mapping

from hypervector.data.hl_events import L2SnapshotEvent, PublicTradeEvent
from hypervector.execution import OrderCommand, VenueOrderEvent

EXECUTION_MODEL = "nautilus_event_v1"
MARGIN_MODEL = "hyperliquid_isolated_v1"
OrderStatus = Literal["pending", "active", "cancel_pending", "terminal"]


@dataclass
class ShadowOrder:
    """Mutable internal state for one simulated venue order."""

    command: OrderCommand
    activation_ms: int
    status: OrderStatus = "pending"
    activated: bool = False
    cancel_effective_ms: int | None = None
    cumulative_quantity: float = 0.0
    queue_ahead_quantity: float = 0.0

    @property
    def remaining_quantity(self) -> float:
        """Return unfilled order quantity."""
        return max(0.0, self.command.quantity - self.cumulative_quantity)


@dataclass(frozen=True)
class ShadowOrderTelemetry:
    """Latest auditable execution evidence for one shadow order."""

    client_order_id: str
    execution_model: str
    data_source: str | None
    evidence_fresh: bool
    configured_submit_latency_ms: int
    configured_cancel_latency_ms: int
    queue_ahead_quantity: float
    requested_quantity: float
    cumulative_filled_quantity: float
    remaining_quantity: float
    status: str
    margin_model: str


@dataclass(frozen=True)
class ShadowExecutionRecord:
    """One fill plus the evidence metadata absent from the venue event type."""

    event: VenueOrderEvent
    execution_model: str
    data_source: str
    evidence_fresh: bool
    event_freshness_ms: float
    configured_latency_ms: int
    queue_ahead_quantity: float
    requested_quantity: float
    cumulative_filled_quantity: float
    remaining_quantity: float
    liquidity_side: str
    margin_model: str


@dataclass(frozen=True)
class ShadowLiquidation:
    """Auditable result of one isolated mark-price liquidation."""

    symbol: str
    observed_at: str
    mark_price: float
    boundary_price: float
    position_quantity: float
    isolated_margin_usd: float
    position_equity_usd: float
    maintenance_margin_usd: float
    execution_fee_usd: float
    clearance_fee_usd: float
    execution_model: str
    method: Literal["market", "backstop"]
    attempted_quantity: float
    filled_quantity: float
    remaining_quantity: float
    execution_price: float
    partial_rule_applied: bool
    cooldown_until_ms: int | None
    market_filled_quantity: float
    backstop_quantity: float
    margin_mode: Literal["isolated"] = "isolated"


def order_telemetry(
    order: ShadowOrder,
    *,
    source: str | None,
    evidence_fresh: bool,
    submit_latency_ms: int,
    cancel_latency_ms: int,
) -> ShadowOrderTelemetry:
    """Project internal order state into auditable public telemetry."""
    return ShadowOrderTelemetry(
        client_order_id=order.command.client_order_id,
        execution_model=EXECUTION_MODEL,
        data_source=source,
        evidence_fresh=evidence_fresh,
        configured_submit_latency_ms=submit_latency_ms,
        configured_cancel_latency_ms=cancel_latency_ms,
        queue_ahead_quantity=order.queue_ahead_quantity,
        requested_quantity=order.command.quantity,
        cumulative_filled_quantity=order.cumulative_quantity,
        remaining_quantity=order.remaining_quantity,
        status=order.status,
        margin_model=MARGIN_MODEL,
    )


def shadow_unrealized_pnl(
    quantity: float,
    average_price: float | None,
    mark_price: float,
) -> float:
    """Return signed linear-perpetual unrealized PnL."""
    if average_price is None:
        return 0.0
    side = 1.0 if quantity > 0.0 else -1.0
    return side * abs(quantity) * (mark_price - average_price)


def shadow_marked_equity(
    realized_equity: float,
    quantity: float,
    average_price: float | None,
    mark_price: float | None,
) -> float:
    """Return equity at the latest available mark."""
    if mark_price is None:
        return realized_equity
    return realized_equity + shadow_unrealized_pnl(
        quantity,
        average_price,
        mark_price,
    )


def queue_ahead(
    order: ShadowOrder,
    book: L2SnapshotEvent,
    orders: tuple[ShadowOrder, ...],
) -> float:
    """Return displayed and earlier simulated liquidity at one price level."""
    limit = order.command.limit_price
    if limit is None:
        return 0.0
    levels = book.bids if order.command.side == "buy" else book.asks
    displayed = sum(level.size for level in levels if abs(level.price - limit) <= 1e-12)
    earlier = sum(
        item.remaining_quantity
        for item in orders
        if item is not order
        and item.status in {"active", "cancel_pending"}
        and item.command.side == order.command.side
        and item.command.limit_price == limit
    )
    return displayed + earlier


def matching_orders(
    orders: Mapping[str, ShadowOrder],
    trade: PublicTradeEvent,
) -> tuple[ShadowOrder, ...]:
    """Return active maker orders eligible for one aggressor trade."""
    matches: list[ShadowOrder] = []
    for order in orders.values():
        limit = order.command.limit_price
        if not order.activated or order.status not in {"active", "cancel_pending"}:
            continue
        if limit is None:
            continue
        buy_match = order.command.side == "buy" and trade.aggressor_side == "sell"
        sell_match = order.command.side == "sell" and trade.aggressor_side == "buy"
        if (buy_match and trade.price <= limit) or (
            sell_match and trade.price >= limit
        ):
            matches.append(order)
    return tuple(matches)


def would_cross(command: OrderCommand, book: L2SnapshotEvent) -> bool:
    """Return whether a post-only limit would take the current touch."""
    if command.limit_price is None:
        return False
    if command.side == "buy":
        return command.limit_price >= book.asks[0].price
    return command.limit_price <= book.bids[0].price


def known_open_order(
    orders: Mapping[str, ShadowOrder],
    client_order_id: str,
) -> ShadowOrder:
    """Return one known non-terminal order or fail explicitly."""
    order = orders.get(client_order_id)
    if order is None:
        raise KeyError(client_order_id)
    if order.status == "terminal":
        raise ValueError(f"order {client_order_id!r} is already terminal")
    return order


def state_event(
    client_order_id: str,
    event_type: Literal[
        "submitted", "accepted", "rejected", "cancel_pending", "canceled"
    ],
    event_at: str,
    *,
    reason: str | None = None,
    cumulative: float = 0.0,
) -> VenueOrderEvent:
    """Construct one normalized non-fill order transition."""
    return VenueOrderEvent(
        client_order_id=client_order_id,
        venue_order_id=f"shadow-{client_order_id}",
        event_type=event_type,
        event_at=event_at,
        last_quantity=0.0,
        cumulative_quantity=cumulative,
        fill_price=None,
        fee_usd=0.0,
        liquidity_side=None,
        reason=reason,
    )


def fill_event(
    order: ShadowOrder,
    trade: PublicTradeEvent,
    quantity: float,
    fee: float,
    final: bool,
) -> VenueOrderEvent:
    """Construct one normalized maker-fill transition."""
    return VenueOrderEvent(
        client_order_id=order.command.client_order_id,
        venue_order_id=f"shadow-{order.command.client_order_id}",
        event_type="filled" if final else "partially_filled",
        event_at=iso_ms(trade.exchange_ts_ms),
        last_quantity=quantity,
        cumulative_quantity=order.cumulative_quantity,
        fill_price=order.command.limit_price or trade.price,
        fee_usd=fee,
        liquidity_side="maker",
        reason=None,
    )


def timestamp_ms(value: str) -> int:
    """Parse an explicit UTC timestamp into epoch milliseconds."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0.0:
        raise ValueError("timestamp must include an explicit UTC offset")
    return int(parsed.timestamp() * 1_000)


def iso_ms(value: int) -> str:
    """Render epoch milliseconds as explicit UTC ISO-8601."""
    return datetime.fromtimestamp(value / 1_000, tz=UTC).isoformat()


def iso_ns(value: int) -> str:
    """Render epoch nanoseconds as explicit UTC ISO-8601."""
    return datetime.fromtimestamp(value / 1_000_000_000, tz=UTC).isoformat()


def positive(value: float, name: str) -> None:
    """Require one positive finite float."""
    finite(value, name)
    if value <= 0.0:
        raise ValueError(f"{name} must be positive")


def rate(value: float, name: str) -> None:
    """Require one finite decimal rate in the half-open unit interval."""
    finite(value, name)
    if value < 0.0 or value >= 1.0:
        raise ValueError(f"{name} must be within [0, 1)")


def positive_rate(value: float, name: str) -> None:
    """Require one positive finite decimal rate below one."""
    rate(value, name)
    if value == 0.0:
        raise ValueError(f"{name} must be positive")


def finite(value: float, name: str) -> None:
    """Require one finite numeric value."""
    if isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def nonempty(value: str, name: str) -> None:
    """Require one non-empty text value."""
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")
