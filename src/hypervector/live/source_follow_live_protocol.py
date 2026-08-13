"""Venue boundary for the source-follow live execution engine."""

from __future__ import annotations

from typing import Protocol

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolBookSnapshot,
    SolFundingPayment,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)


class SourceFollowVenueProtocol(Protocol):
    """Venue operations required by the target-only BTC lifecycle."""

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight: ...

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot: ...

    def configure_isolated_leverage(self, leverage: int) -> None: ...

    def reconcile(self) -> SolReconciliationSnapshot: ...

    def submit_entry(self, **kwargs: object) -> HyperliquidOrderAck: ...

    def submit_target(self, **kwargs: object) -> HyperliquidOrderAck: ...

    def cancel_order(self, oid: int) -> HyperliquidOrderAck: ...

    def close_position(self, **kwargs: object) -> HyperliquidOrderAck: ...

    def funding_payments(self, **kwargs: int) -> tuple[SolFundingPayment, ...]: ...
