"""Pure order-identity decisions for the Apex MM live lifecycle."""

from __future__ import annotations

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
    SolOpenOrder,
)
from hypervector.research.apex_regime_mm_policy import ApexMMQuote


def quote_replacement_required(
    *,
    open_orders: tuple[SolOpenOrder, ...],
    quote: ApexMMQuote,
    current_position_size: float,
    quoted_position_size: float,
) -> bool:
    """Return whether current venue orders differ materially from a new quote."""
    if current_position_size != quoted_position_size:
        return True
    expected: dict[str, float] = {}
    if quote.bid_price is not None and quote.bid_size > 0.0:
        expected["B"] = quote.bid_price
    if quote.ask_price is not None and quote.ask_size > 0.0:
        expected["A"] = quote.ask_price
    observed: dict[str, float] = {}
    for order in open_orders:
        if order.side in observed or order.limit_price is None:
            return True
        observed[order.side] = order.limit_price
    return observed != expected


def recovered_order_ack(status: HyperliquidOrderStatus) -> HyperliquidOrderAck:
    """Convert an exact order-status lookup into a recovered acknowledgement."""
    accepted = status.status in {"filled", "open"}
    return HyperliquidOrderAck(
        accepted,
        status.oid,
        status.status,
        filled_size=status.size if status.status == "filled" else None,
        error=None if accepted else status.status,
        client_order_id=status.client_order_id,
        recovered_after_transport_error=True,
        venue_timestamp_ms=status.status_timestamp_ms,
    )


def recovered_cancel_ack(status: HyperliquidOrderStatus) -> HyperliquidOrderAck:
    """Treat an exact filled/canceled status as a completed cancel objective."""
    accepted = status.status in {"filled", "canceled"}
    return HyperliquidOrderAck(
        accepted,
        status.oid,
        status.status,
        filled_size=status.size if status.status == "filled" else None,
        error=None if accepted else status.status,
        client_order_id=status.client_order_id,
        venue_timestamp_ms=status.status_timestamp_ms,
    )
