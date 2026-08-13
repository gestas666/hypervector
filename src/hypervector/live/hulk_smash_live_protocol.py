"""Venue mutation boundary for the explicitly armed Hulk canary."""

from __future__ import annotations

from typing import Protocol

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
    SolBookSnapshot,
    SolFundingPayment,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)


class HulkSmashVenueProtocol(Protocol):
    """Exact read and order operations required by the bracket lifecycle."""

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight: ...

    def configure_isolated_leverage(self, leverage: int) -> None: ...

    def reconcile(self) -> SolReconciliationSnapshot: ...

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot: ...

    def funding_payments(
        self, *, start_time_ms: int, end_time_ms: int
    ) -> tuple[SolFundingPayment, ...]: ...

    def submit_market_entry(self, **kwargs: object) -> HyperliquidOrderAck: ...

    def place_protective_stop(self, **kwargs: object) -> HyperliquidOrderAck: ...

    def submit_target(self, **kwargs: object) -> HyperliquidOrderAck: ...

    def cancel_order(self, oid: int) -> HyperliquidOrderAck: ...

    def close_position(self, **kwargs: object) -> HyperliquidOrderAck: ...

    def order_status_by_client_id(
        self, client_order_id: str
    ) -> HyperliquidOrderStatus: ...

    def order_status(self, oid: int) -> HyperliquidOrderStatus: ...
