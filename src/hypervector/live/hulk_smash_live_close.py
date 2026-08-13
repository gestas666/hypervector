"""Protected close coordination for the Hulk Smash live lifecycle."""

from __future__ import annotations

from dataclasses import dataclass

from hypervector.live.hulk_smash_live_models import HulkSmashLiveSnapshot
from hypervector.live.hulk_smash_live_orders import (
    HulkSmashOrderAmbiguityError,
    HulkSmashOrderError,
    HulkSmashOrderGateway,
)
from hypervector.live.hulk_smash_live_protocol import HulkSmashVenueProtocol
from hypervector.live.hulk_smash_live_reconcile import HulkSmashReconciler
from hypervector.live.hulk_smash_live_restart import has_stop
from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot


class HulkSmashCloseError(RuntimeError):
    """A Hulk close could not reach a venue-verified safe state."""


class HulkSmashProtectedExposureError(HulkSmashCloseError):
    """A close is unresolved, but the exact protective stop remains active."""


@dataclass(frozen=True)
class HulkSmashCloseResult:
    """Venue truth after a close attempt or an intervening bracket fill."""

    venue: SolReconciliationSnapshot
    oid: int | None
    response_ambiguous: bool
    bracket_exit: bool = False


class HulkSmashCloseCoordinator:
    """Close exposure without canceling its protective stop prematurely."""

    def __init__(
        self,
        *,
        adapter: HulkSmashVenueProtocol,
        orders: HulkSmashOrderGateway,
        reconciler: HulkSmashReconciler,
    ) -> None:
        self._adapter = adapter
        self._orders = orders
        self._reconciler = reconciler

    def close_scheduled(
        self,
        snapshot: HulkSmashLiveSnapshot,
        venue: SolReconciliationSnapshot,
    ) -> HulkSmashCloseResult:
        """Cancel only the target, preserving the stop until flat is verified."""
        stop_oid = _required_oid(snapshot.stop_oid, "stop")
        target_oid = _required_oid(snapshot.target_oid, "target")
        _require_owned_orders(venue, {stop_oid, target_oid})
        self._orders.cancel_order(target_oid, "cancel_target_for_close")
        result = self._reconciler.until(
            lambda current: current.position.size_signed == 0.0
            or not _has_order(current, target_oid)
        )
        if not result.matched:
            raise HulkSmashCloseError("target cancellation did not converge")
        if result.snapshot.position.size_signed == 0.0:
            return HulkSmashCloseResult(result.snapshot, None, False, True)
        _require_protected(result.snapshot, stop_oid)
        return self._close_position(result.snapshot, stop_oid, allow_retry=False)

    def close_emergency(
        self,
        snapshot: HulkSmashLiveSnapshot,
        venue: SolReconciliationSnapshot,
    ) -> HulkSmashCloseResult:
        """Flatten urgently while retaining any exact stop until flat."""
        owned = {oid for oid in (snapshot.stop_oid, snapshot.target_oid) if oid}
        _require_owned_orders(venue, owned)
        target_oid = snapshot.target_oid
        if target_oid is not None and _has_order(venue, target_oid):
            self._orders.cancel_order(target_oid, "emergency_cancel_target")
            venue = self._after_target_cancel(target_oid)
        if venue.position.size_signed == 0.0:
            return self._clear_flat_orders(venue, owned, None, False)
        stop_oid = (
            snapshot.stop_oid if has_stop(venue, snapshot.stop_oid or 0) else None
        )
        return self._close_position(venue, stop_oid, allow_retry=stop_oid is None)

    def _after_target_cancel(self, target_oid: int) -> SolReconciliationSnapshot:
        result = self._reconciler.until(
            lambda current: current.position.size_signed == 0.0
            or not _has_order(current, target_oid)
        )
        if not result.matched:
            raise HulkSmashCloseError("emergency target cancellation did not converge")
        return result.snapshot

    def _close_position(
        self,
        venue: SolReconciliationSnapshot,
        stop_oid: int | None,
        *,
        allow_retry: bool,
    ) -> HulkSmashCloseResult:
        ambiguous = False
        oid: int | None = None
        attempts = 2 if allow_retry else 1
        for _ in range(attempts):
            try:
                ack = self._orders.close_position(
                    position_size_signed=venue.position.size_signed,
                    mark_price=self._adapter.book_snapshot(depth_levels=1).mid_price,
                    operation="reduce_only_close",
                )
                oid = ack.oid
            except HulkSmashOrderAmbiguityError:
                ambiguous = True
            except HulkSmashOrderError as exc:
                raise HulkSmashCloseError(str(exc)) from exc
            result = self._reconciler.until(
                lambda current: current.position.size_signed == 0.0
            )
            if result.matched:
                owned = {stop_oid} if stop_oid is not None else set()
                return self._clear_flat_orders(result.snapshot, owned, oid, ambiguous)
            venue = result.snapshot
            if stop_oid is not None and has_stop(venue, stop_oid):
                raise HulkSmashProtectedExposureError(
                    "close remains unresolved with protected exposure"
                )
        raise HulkSmashCloseError("emergency close left unprotected exposure")

    def _clear_flat_orders(
        self,
        venue: SolReconciliationSnapshot,
        owned: set[int],
        oid: int | None,
        ambiguous: bool,
    ) -> HulkSmashCloseResult:
        _require_owned_orders(venue, owned)
        for order in venue.open_orders:
            self._orders.cancel_order(order.oid, "cancel_residual_stop_after_close")
        if venue.open_orders:
            result = self._reconciler.until(lambda current: current.is_flat)
            if not result.matched:
                raise HulkSmashCloseError("residual stop cancellation did not converge")
            venue = result.snapshot
        return HulkSmashCloseResult(venue, oid, ambiguous)


def _required_oid(value: int | None, label: str) -> int:
    if value is None or value <= 0:
        raise HulkSmashCloseError(f"{label} order identity is unavailable")
    return value


def _has_order(venue: SolReconciliationSnapshot, oid: int) -> bool:
    return any(order.oid == oid for order in venue.open_orders)


def _require_owned_orders(
    venue: SolReconciliationSnapshot,
    owned: set[int],
) -> None:
    unknown = [order.oid for order in venue.open_orders if order.oid not in owned]
    if unknown:
        raise HulkSmashCloseError(f"close found unowned orders: {unknown}")


def _require_protected(venue: SolReconciliationSnapshot, stop_oid: int) -> None:
    if not has_stop(venue, stop_oid):
        raise HulkSmashCloseError("close preparation removed protective stop")
