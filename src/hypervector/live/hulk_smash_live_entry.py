"""Ambiguity-safe entry coordination for Hulk Smash live execution."""

from __future__ import annotations

from hypervector.live.hulk_smash_live_decisions import HulkSmashLiveDecision
from hypervector.live.hulk_smash_live_orders import (
    HulkSmashOrderAmbiguityError,
    HulkSmashOrderError,
    HulkSmashOrderGateway,
)
from hypervector.live.hulk_smash_live_reconcile import HulkSmashReconciler
from hypervector.live.hulk_smash_live_risk import HulkProtectionPlan
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolReconciliationSnapshot,
)


class HulkSmashEntryError(RuntimeError):
    """A Hulk entry could not reach an attributable venue state."""


class HulkSmashEntryExposureError(HulkSmashEntryError):
    """An entry failure left venue exposure that requires urgent flattening."""

    def __init__(self, reason: str, venue: SolReconciliationSnapshot) -> None:
        self.venue = venue
        super().__init__(reason)


class HulkSmashEntryCoordinator:
    """Submit one entry and resolve status or account-state ambiguity."""

    def __init__(
        self,
        *,
        orders: HulkSmashOrderGateway,
        reconciler: HulkSmashReconciler,
    ) -> None:
        self._orders = orders
        self._reconciler = reconciler

    def submit(
        self,
        plan: HulkProtectionPlan,
        decision: HulkSmashLiveDecision,
    ) -> HyperliquidOrderAck:
        """Return an exact acknowledgement or resolve ambiguous venue state."""
        try:
            return self._orders.submit_entry(plan, decision)
        except HulkSmashOrderAmbiguityError as exc:
            self._resolve_ambiguity(str(exc))
        except HulkSmashOrderError as exc:
            raise HulkSmashEntryError(str(exc)) from exc

    def confirm(
        self,
        acknowledgement: HyperliquidOrderAck,
    ) -> SolReconciliationSnapshot:
        """Require the acknowledged entry to become short venue exposure."""
        result = self._reconciler.until(lambda venue: venue.position.size_signed < 0.0)
        if not result.matched:
            self._resolve_timeout(acknowledgement, result.snapshot)
        return result.snapshot

    def _resolve_ambiguity(self, reason: str) -> None:
        result = self._reconciler.until(
            lambda venue: venue.position.size_signed != 0.0 or bool(venue.open_orders)
        )
        venue = result.snapshot
        if venue.position.size_signed != 0.0:
            raise HulkSmashEntryExposureError(f"ambiguous entry: {reason}", venue)
        if venue.open_orders:
            ids = [order.oid for order in venue.open_orders]
            raise HulkSmashEntryError(
                f"ambiguous entry produced unowned open orders: {ids}"
            )
        raise HulkSmashEntryError(f"ambiguous entry had no venue exposure: {reason}")

    def _resolve_timeout(
        self,
        acknowledgement: HyperliquidOrderAck,
        venue: SolReconciliationSnapshot,
    ) -> None:
        if venue.position.size_signed != 0.0:
            raise HulkSmashEntryExposureError(
                "entry exposure appeared without convergence",
                venue,
            )
        for order in venue.open_orders:
            if order.oid != acknowledgement.oid:
                raise HulkSmashEntryError(
                    f"entry timeout found unowned order {order.oid}"
                )
            try:
                self._orders.cancel_order(order.oid, "cancel_ambiguous_entry")
            except HulkSmashOrderError as exc:
                raise HulkSmashEntryError(str(exc)) from exc
        if venue.open_orders:
            result = self._reconciler.until(lambda current: current.is_flat)
            if not result.matched:
                raise HulkSmashEntryError("entry cancellation did not converge")
        raise HulkSmashEntryError("accepted entry was not venue-confirmed")
