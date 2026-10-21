"""Bounded post-write reconciliation for Hyperliquid live operations."""

from __future__ import annotations

from collections.abc import Callable
import math

from hypervector.live.hyperliquid_protocol import (
    HyperliquidLiveAdapterProtocol,
    HyperliquidReconciliationSnapshot,
)
from hypervector.live.asset_state import AssetLiveSnapshot, AssetLiveState
from hypervector.live.asset_protective_order import protective_stop_covers
from hypervector.live.asset_execution_evidence import partial_close_size
from hypervector.live.asset_reconcile import (
    RecoveredAssetOwnership,
    owned_protective_stop_fill,
)


class AssetReconciliationPolicyError(ValueError):
    """The bounded venue-consistency policy is malformed."""


class AssetReconciliationPoller:
    """Retry venue reads only within one explicit bounded consistency window."""

    def __init__(
        self,
        *,
        adapter: HyperliquidLiveAdapterProtocol,
        attempts: int,
        delay_seconds: float,
        sleep_fn: Callable[[float], None],
        before_retry: Callable[[], None] | None = None,
    ) -> None:
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1:
            raise AssetReconciliationPolicyError("reconciliation attempts must be positive")
        if not math.isfinite(delay_seconds) or delay_seconds < 0.0:
            raise AssetReconciliationPolicyError(
                "reconciliation delay must be nonnegative and finite"
            )
        self._adapter = adapter
        self._attempts = attempts
        self._delay_seconds = delay_seconds
        self._sleep_fn = sleep_fn
        self._before_retry = before_retry

    def wait_for(
        self,
        condition: Callable[[HyperliquidReconciliationSnapshot], bool],
    ) -> HyperliquidReconciliationSnapshot:
        """Return the first matching snapshot or the final bounded observation."""
        latest = self._adapter.reconcile()
        for _ in range(1, self._attempts):
            if condition(latest):
                return latest
            self._sleep_fn(self._delay_seconds)
            if self._before_retry is not None:
                self._before_retry()
            latest = self._adapter.reconcile()
        return latest

    def wait_for_state(self, state: AssetLiveSnapshot) -> HyperliquidReconciliationSnapshot:
        """Wait for venue visibility matching a local FLAT or OPEN lifecycle."""
        if state.state is AssetLiveState.FLAT:
            return self.wait_for(lambda venue: venue.is_flat)
        if state.state is not AssetLiveState.OPEN or state.stop_oid is None:
            return self._adapter.reconcile()
        return self.wait_for(
            lambda venue: _open_visible(state, venue) or protective_stop_fill_visible(state, venue)
        )

    def wait_for_close(self, state: AssetLiveSnapshot, close_oid: int) -> HyperliquidReconciliationSnapshot:
        """Wait for flat or a partial reduction with complete exact-order fill evidence."""
        return self.wait_for(
            lambda venue: venue.position.size_signed == 0.0
            or partial_close_size(state, venue, close_oid) is not None
        )


def protected_order_visible(
    venue: HyperliquidReconciliationSnapshot,
    *,
    stop_oid: int,
    position_size_signed: float,
) -> bool:
    """Report whether the expected reduce-only trigger is venue-visible."""
    return any(
        order.oid == stop_oid and protective_stop_covers(order, position_size_signed)
        for order in venue.open_orders
    )


def protective_stop_fill_visible(
    state: AssetLiveSnapshot,
    venue: HyperliquidReconciliationSnapshot,
) -> bool:
    """Report whether the exact locally owned stop fully flattened the venue."""
    if (
        state.state is not AssetLiveState.OPEN
        or state.entry_oid is None
        or state.stop_oid is None
        or state.opened_at_ms is None
    ):
        return False
    ownership = RecoveredAssetOwnership(
        state.entry_oid,
        state.stop_oid,
        state.position_size_signed,
        state.opened_at_ms,
        protective_progress=state.protective_progress,
    )
    return owned_protective_stop_fill(ownership, venue)


def _open_visible(
    state: AssetLiveSnapshot,
    venue: HyperliquidReconciliationSnapshot,
) -> bool:
    if state.stop_oid is None:
        return False
    return math.isclose(
        venue.position.size_signed,
        state.position_size_signed,
        rel_tol=0.0,
        abs_tol=1e-9,
    ) and protected_order_visible(
        venue,
        stop_oid=state.stop_oid,
        position_size_signed=state.position_size_signed,
    )
