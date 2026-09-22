"""Adapt the symbol-parameterized venue client to the directional engine."""

from __future__ import annotations

from hypervector.live.entry_submission_deadline import EntrySubmissionDeadline
from hypervector.live.hyperliquid_btc_adapter import BtcHyperliquidAdapter
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
    SolBookSnapshot,
    SolFundingPayment,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)


class MultiAssetDirectionalAdapter:
    """Expose generic IOC entries while preserving exact delegated venue state."""

    def __init__(self, delegate: BtcHyperliquidAdapter) -> None:
        self._delegate = delegate

    @property
    def symbol(self) -> str:
        """Return the perpetual symbol owned by this adapter."""
        return self._delegate.symbol

    @property
    def perp_dex(self) -> str:
        """Return the exact optional builder-perp namespace."""
        return self._delegate.perp_dex

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight:
        """Return symbol-scoped venue and account facts."""
        return self._delegate.preflight(expected_max_leverage=expected_max_leverage)

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot:
        """Return the symbol's read-only depth snapshot."""
        return self._delegate.book_snapshot(depth_levels=depth_levels)

    def configure_isolated_leverage(self, leverage: int) -> None:
        """Configure symbol-scoped isolated leverage."""
        self._delegate.configure_isolated_leverage(leverage)

    def submit_entry(
        self,
        *,
        side: str,
        requested_notional_usd: float,
        mark_price: float,
        client_order_id: str,
        entry_deadline: EntrySubmissionDeadline | None = None,
    ) -> HyperliquidOrderAck:
        """Submit one cap-checked IOC directional entry."""
        return self._delegate.submit_market_entry(
            side=side,
            requested_notional_usd=requested_notional_usd,
            mark_price=mark_price,
            client_order_id=client_order_id,
            **(
                {"entry_deadline": entry_deadline} if entry_deadline is not None else {}
            ),
        )

    def place_protective_stop(
        self,
        *,
        position_size_signed: float,
        trigger_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        """Place one venue-native reduce-only stop."""
        return self._delegate.place_protective_stop(
            position_size_signed=position_size_signed,
            trigger_price=trigger_price,
            client_order_id=client_order_id,
        )

    def submit_target(
        self,
        *,
        position_size_signed: float,
        limit_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        """Place one symbol-scoped reduce-only post-only target."""
        return self._delegate.submit_target(
            position_size_signed=position_size_signed,
            limit_price=limit_price,
            client_order_id=client_order_id,
        )

    def modify_protective_stop(
        self,
        *,
        oid: int,
        position_size_signed: float,
        trigger_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        """Move one owned reduce-only stop to a new trigger."""
        return self._delegate.modify_protective_stop(
            oid=oid,
            position_size_signed=position_size_signed,
            trigger_price=trigger_price,
            client_order_id=client_order_id,
        )

    def cancel_order(self, oid: int) -> HyperliquidOrderAck:
        """Cancel one symbol-scoped order."""
        return self._delegate.cancel_order(oid)

    def close_position(
        self,
        *,
        position_size_signed: float,
        mark_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        """Submit one reduce-only IOC close."""
        return self._delegate.close_position(
            position_size_signed=position_size_signed,
            mark_price=mark_price,
            client_order_id=client_order_id,
        )

    def reconcile(self) -> SolReconciliationSnapshot:
        """Return symbol exposure with shared account totals."""
        return self._delegate.reconcile()

    def invalidate_reconciliation_cache(self) -> None:
        """Discard shared account truth before a bounded consistency retry."""
        self._delegate.invalidate_reconciliation_cache()

    def order_status(self, oid: int) -> HyperliquidOrderStatus:
        """Return one exact venue order status."""
        return self._delegate.order_status(oid)

    def order_status_by_client_id(
        self,
        client_order_id: str,
    ) -> HyperliquidOrderStatus:
        """Return one exact order by durable client identity."""
        return self._delegate.order_status_by_client_id(client_order_id)

    def funding_payments(
        self,
        *,
        start_time_ms: int,
        end_time_ms: int,
    ) -> tuple[SolFundingPayment, ...]:
        """Return exact symbol funding ledger updates."""
        return self._delegate.funding_payments(
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )
