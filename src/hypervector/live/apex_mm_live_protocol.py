"""Typed venue and telemetry boundaries for the Apex MM live canary."""

from __future__ import annotations

from typing import Protocol

from hypervector.live.apex_mm_live_models import ApexMMLiveSnapshot
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
    HyperliquidPostOnlyOrder,
    SolBookSnapshot,
    SolFundingPayment,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)
from hypervector.research.apex_regime_mm_policy import ApexMMQuote


class ApexMMVenueProtocol(Protocol):
    """Venue operations required by paired post-only BTC quoting."""

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight: ...

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot: ...

    def configure_isolated_leverage(self, leverage: int) -> None: ...

    def reconcile(self) -> SolReconciliationSnapshot: ...

    def submit_entry(self, **kwargs: object) -> HyperliquidOrderAck: ...

    def submit_post_only_batch(
        self,
        orders: tuple[HyperliquidPostOnlyOrder, ...],
    ) -> tuple[HyperliquidOrderAck, ...]: ...

    def cancel_order(self, oid: int) -> HyperliquidOrderAck: ...

    def close_position(self, **kwargs: object) -> HyperliquidOrderAck: ...

    def wait_for_fill(
        self,
        oid: int,
        markout_horizon_ms: int,
    ) -> tuple[SolReconciliationSnapshot, SolBookSnapshot]: ...

    def order_status(self, oid: int) -> HyperliquidOrderStatus: ...

    def order_status_by_client_id(
        self,
        client_order_id: str,
    ) -> HyperliquidOrderStatus: ...

    def funding_payments(
        self,
        **kwargs: int,
    ) -> tuple[SolFundingPayment, ...]: ...

    def begin_shutdown(self) -> None: ...


class ApexMMTelemetryProtocol(Protocol):
    """Secret-free backend facts emitted by the live lifecycle."""

    def emit_preflight(
        self,
        preflight: SolVenuePreflight,
        venue: SolReconciliationSnapshot,
    ) -> None: ...

    def emit_reconciliation(self, venue: SolReconciliationSnapshot) -> None: ...

    def emit_book(self, book: SolBookSnapshot) -> None: ...

    def emit_quote(
        self,
        quote: ApexMMQuote,
        inventory_notional_usd: float,
    ) -> None: ...

    def emit_order_intent(self, **payload: object) -> None: ...

    def emit_ack(self, operation: str, ack: HyperliquidOrderAck) -> None: ...

    def emit_funding_payments(
        self,
        payments: tuple[SolFundingPayment, ...],
    ) -> None: ...

    def emit_state(self, snapshot: ApexMMLiveSnapshot) -> None: ...

    def emit_fault(self, message: str) -> None: ...
