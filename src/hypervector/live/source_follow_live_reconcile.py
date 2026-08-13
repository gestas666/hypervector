"""Pure reconciliation helpers for the BTC source-follow live lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from hypervector.live.hyperliquid_protocol import (
    SolOpenOrder,
    SolReconciliationSnapshot,
)


class ReconciliationReader(Protocol):
    """Venue boundary needed by bounded reconciliation waits."""

    def reconcile(self) -> SolReconciliationSnapshot:
        """Return the latest venue-authoritative account state."""


def wait_for_target(
    adapter: ReconciliationReader,
    *,
    target_oid: int,
    attempts: int,
    delay_seconds: float,
    sleep_fn: Callable[[float], None],
) -> SolReconciliationSnapshot:
    """Wait until a target is visible or its position is already flat."""
    latest = adapter.reconcile()
    for _ in range(1, attempts):
        visible = any(order.oid == target_oid for order in latest.open_orders)
        if visible or latest.position.size_signed == 0.0:
            return latest
        sleep_fn(delay_seconds)
        latest = adapter.reconcile()
    return latest


def wait_for_flat(
    adapter: ReconciliationReader,
    *,
    attempts: int,
    delay_seconds: float,
    sleep_fn: Callable[[float], None],
) -> SolReconciliationSnapshot:
    """Wait a bounded interval for venue-confirmed flat exposure."""
    latest = adapter.reconcile()
    for _ in range(1, attempts):
        if latest.position.size_signed == 0.0:
            return latest
        sleep_fn(delay_seconds)
        latest = adapter.reconcile()
    return latest


def target_fill_matches(
    venue: SolReconciliationSnapshot,
    *,
    target_oid: int | None,
    position_size: float,
) -> bool:
    """Return whether venue fills prove the owned target closed this side."""
    if target_oid is None:
        return False
    position_side = "long" if position_size > 0.0 else "short"
    return any(
        fill.oid == target_oid and f"close {position_side}" in fill.direction.lower()
        for fill in venue.fills
    )


def target_matches(position_size: float, target: SolOpenOrder) -> bool:
    """Return whether one reduce-only order covers the reconciled exposure."""
    expected_side = "A" if position_size > 0.0 else "B"
    return (
        not target.is_trigger
        and target.side == expected_side
        and abs(target.size - abs(position_size)) <= 1e-9
    )


def target_price(
    *,
    entry_price: float,
    position_size: float,
    target_margin_pct: float,
    leverage: float,
) -> float:
    """Return the unrounded target implied by gross margin return."""
    fraction = target_margin_pct / leverage / 100.0
    direction = 1.0 if position_size > 0.0 else -1.0
    return entry_price * (1.0 + direction * fraction)


def opened_at_ms(
    venue: SolReconciliationSnapshot,
    *,
    snapshot_opened_at_ms: int | None,
    fallback_ms: int,
) -> int:
    """Recover the current position's newest matching entry timestamp."""
    if snapshot_opened_at_ms is not None:
        return snapshot_opened_at_ms
    position_side = "long" if venue.position.size_signed > 0.0 else "short"
    entries = [
        fill.timestamp_ms
        for fill in venue.fills
        if f"open {position_side}" in fill.direction.lower()
    ]
    return max(entries, default=fallback_ms)


def duration_reached(
    *,
    observed_at_ms: int,
    started_at_ms: int,
    duration_seconds: float,
) -> bool:
    """Return whether a monotonic venue lifecycle duration has elapsed."""
    return observed_at_ms - started_at_ms >= int(duration_seconds * 1_000)
