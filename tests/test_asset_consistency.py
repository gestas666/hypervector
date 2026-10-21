"""Tests for bounded post-write venue reconciliation."""

from __future__ import annotations

from hypervector.live.hyperliquid_protocol import (
    HyperliquidAccountSnapshot,
    HyperliquidOpenOrder,
    HyperliquidPositionSnapshot,
    HyperliquidReconciliationSnapshot,
)
from hypervector.live.asset_consistency import AssetReconciliationPoller


class _CachedAdapter:
    """Expose stale truth until the caller invalidates its read cache."""

    def __init__(
        self,
        stale: HyperliquidReconciliationSnapshot,
        fresh: HyperliquidReconciliationSnapshot,
    ) -> None:
        self._stale = stale
        self._fresh = fresh
        self._invalidated = False
        self.reconcile_calls = 0
        self.invalidate_calls = 0

    def reconcile(self) -> HyperliquidReconciliationSnapshot:
        """Return the currently cached venue observation."""
        self.reconcile_calls += 1
        return self._fresh if self._invalidated else self._stale

    def invalidate(self) -> None:
        """Make the next reconciliation observe refreshed venue truth."""
        self.invalidate_calls += 1
        self._invalidated = True


def test_wait_for_invalidates_cached_truth_before_retry() -> None:
    """A bounded retry must not re-check one stale post-write snapshot."""
    stale = _venue((11,))
    fresh = _venue((11, 22))
    adapter = _CachedAdapter(stale, fresh)
    sleeps: list[float] = []
    poller = AssetReconciliationPoller(
        adapter=adapter,
        attempts=4,
        delay_seconds=0.25,
        sleep_fn=sleeps.append,
        before_retry=adapter.invalidate,
    )

    observed = poller.wait_for(
        lambda venue: {order.oid for order in venue.open_orders} == {11, 22}
    )

    assert observed is fresh
    assert adapter.reconcile_calls == 2
    assert adapter.invalidate_calls == 1
    assert sleeps == [0.25]


def _venue(order_ids: tuple[int, ...]) -> HyperliquidReconciliationSnapshot:
    position = HyperliquidPositionSnapshot(
        size_signed=0.001,
        entry_price=63_390.0,
        liquidation_price=51_381.0,
        margin_used_usd=5.0,
        position_value_usd=25.0,
        unrealized_pnl_usd=0.0,
        leverage_type="isolated",
        leverage=5,
    )
    account = HyperliquidAccountSnapshot(
        account_value_usd=500.0,
        withdrawable_usd=495.0,
        total_margin_used_usd=5.0,
        total_notional_position_usd=25.0,
        position=position,
    )
    orders = tuple(
        HyperliquidOpenOrder(
            oid=oid,
            size=0.001,
            original_size=0.001,
            side="A",
            reduce_only=True,
            is_trigger=oid == 11,
            trigger_price=63_263.0 if oid == 11 else 0.0,
            order_type="Stop Market" if oid == 11 else "Limit",
            timestamp_ms=1,
            limit_price=63_263.0 if oid == 11 else 63_770.0,
        )
        for oid in order_ids
    )
    return HyperliquidReconciliationSnapshot(account=account, open_orders=orders, fills=())
