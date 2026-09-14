"""Exact venue-order checks for optional shared-lifecycle profit targets."""

from __future__ import annotations

import math

from hypervector.live.hyperliquid_protocol import (
    SolOpenOrder,
    SolReconciliationSnapshot,
)
from hypervector.live.hyperliquid_sol_parsing import normalize_perp_price
from hypervector.live.sol_protective_order import protective_stop_covers
from hypervector.live.sol_protective_execution_evidence import (
    ProtectiveExecutionProgress,
)
from hypervector.live.sol_protective_checkpoint import venue_without_credited_fills

_MAXIMUM_PERP_SIZE_DECIMALS = 6


def target_order_visible(
    venue: SolReconciliationSnapshot,
    *,
    target_oid: int,
    position_size_signed: float,
    target_price: float,
) -> bool:
    """Report whether one exact reduce-only non-trigger target is visible."""
    matching = [order for order in venue.open_orders if order.oid == target_oid]
    return len(matching) == 1 and _target_matches(
        matching[0],
        position_size_signed=position_size_signed,
        target_price=target_price,
    )


def complete_bracket_visible(
    venue: SolReconciliationSnapshot,
    *,
    stop_oid: int,
    target_oid: int,
    position_size_signed: float,
    target_price: float,
) -> bool:
    """Require exact stop/target ownership with no unexplained open order."""
    expected = {stop_oid, target_oid}
    observed = {order.oid for order in venue.open_orders}
    if observed != expected:
        return False
    stop = next(order for order in venue.open_orders if order.oid == stop_oid)
    return protective_stop_covers(stop, position_size_signed) and target_order_visible(
        venue,
        target_oid=target_oid,
        position_size_signed=position_size_signed,
        target_price=target_price,
    )


def owned_exit_reason(
    venue: SolReconciliationSnapshot,
    *,
    stop_oid: int,
    target_oid: int | None,
    position_size_signed: float,
    protective_progress: ProtectiveExecutionProgress = ProtectiveExecutionProgress(),
) -> str | None:
    """Classify a complete close from exact owned stop/target fill identities."""
    if venue.position.size_signed != 0.0:
        return None
    venue = venue_without_credited_fills(venue, protective_progress)
    owned = {stop_oid}
    if target_oid is not None:
        owned.add(target_oid)
    fills = [fill for fill in venue.fills if fill.oid in owned]
    expected_side = "A" if position_size_signed > 0.0 else "B"
    expected_direction = "close long" if position_size_signed > 0.0 else "close short"
    valid = [
        fill
        for fill in fills
        if fill.side == expected_side and fill.direction.strip().lower() == expected_direction
    ]
    if not math.isclose(
        sum(fill.size for fill in valid),
        abs(position_size_signed),
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        return None
    filled_oids = {fill.oid for fill in valid if fill.size > 0.0}
    if filled_oids == {stop_oid}:
        return "protective_stop"
    if target_oid is not None and filled_oids == {target_oid}:
        return "target"
    return "mixed_bracket_exit" if filled_oids else None


def _target_matches(
    order: SolOpenOrder,
    *,
    position_size_signed: float,
    target_price: float,
) -> bool:
    return (
        order.reduce_only
        and not order.is_trigger
        and _close_side(order, position_size_signed)
        and _size_matches(order, position_size_signed)
        and order.limit_price is not None
        and _normalized_target_price_matches(order.limit_price, target_price)
    )


def _normalized_target_price_matches(observed: float, requested: float) -> bool:
    if math.isclose(observed, requested, rel_tol=0.0, abs_tol=1e-12):
        return True
    return any(
        math.isclose(
            observed,
            normalize_perp_price(requested, size_decimals),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        for size_decimals in range(_MAXIMUM_PERP_SIZE_DECIMALS + 1)
    )


def _close_side(order: SolOpenOrder, position_size_signed: float) -> bool:
    expected = "A" if position_size_signed > 0.0 else "B"
    return order.side == expected


def _size_matches(order: SolOpenOrder, position_size_signed: float) -> bool:
    return math.isclose(
        order.size,
        abs(position_size_signed),
        rel_tol=0.0,
        abs_tol=1e-9,
    )
