"""Exact fill attribution for canceled entries and partial position reductions."""

import math

from hypervector.live.hyperliquid_fill_identity import (
    HyperliquidFillIdentityError,
    fill_trade_id,
)
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderStatus,
    SolReconciliationSnapshot,
)
from hypervector.live.sol_range_onset_state import SolLiveSnapshot

QUANTITY_TOLERANCE = 1e-9


def owned_fill_quantity(
    venue: SolReconciliationSnapshot,
    oid: int,
    *,
    position_size_signed: float,
    entering: bool,
    earliest_ms: int,
    latest_ms: int | None = None,
) -> float | None:
    """Sum unique exact-order fills only when every matching row has valid attribution."""
    fills = [fill for fill in venue.fills if fill.oid == oid]
    if not fills:
        return None
    try:
        identities = [fill_trade_id(fill) for fill in fills]
    except HyperliquidFillIdentityError:
        return None
    if len(identities) != len(set(identities)):
        return None
    long = position_size_signed > 0.0
    side = "B" if long == entering else "A"
    direction = f"{'open' if entering else 'close'} {'long' if long else 'short'}"
    if any(
        not math.isfinite(fill.size)
        or fill.size <= 0.0
        or fill.side != side
        or fill.direction.strip().lower() != direction
        or fill.timestamp_ms < earliest_ms
        or (latest_ms is not None and fill.timestamp_ms > latest_ms)
        for fill in fills
    ):
        return None
    return math.fsum(fill.size for fill in fills)


def partial_close_size(
    before: SolLiveSnapshot, venue: SolReconciliationSnapshot, close_oid: int
) -> float | None:
    """Return a same-direction remainder explained exactly by one owned close order."""
    original, remaining = before.position_size_signed, venue.position.size_signed
    if (
        before.opened_at_ms is None
        or not math.isfinite(remaining)
        or original * remaining <= 0.0
        or abs(remaining) >= abs(original)
    ):
        return None
    filled = owned_fill_quantity(
        venue,
        close_oid,
        position_size_signed=original,
        entering=False,
        earliest_ms=before.opened_at_ms,
    )
    if filled is None or not math.isclose(
        filled + abs(remaining),
        abs(original),
        rel_tol=0.0,
        abs_tol=QUANTITY_TOLERANCE,
    ):
        return None
    return remaining


def canceled_entry_fill_size(
    status: HyperliquidOrderStatus, venue: SolReconciliationSnapshot
) -> float | None:
    """Confirm executed entry quantity from fills and exposure, never from remaining sz."""
    return _canceled_fill_size(status, venue, entering=True)


def canceled_close_fill_size(
    status: HyperliquidOrderStatus, venue: SolReconciliationSnapshot
) -> float | None:
    """Recognize a partial close only when exact fills and remainder explain its request."""
    return _canceled_fill_size(status, venue, entering=False)


def canceled_close_has_no_observed_fill(
    status: HyperliquidOrderStatus, venue: SolReconciliationSnapshot
) -> bool:
    """Recognize unchanged requested exposure with no observed fill of the canceled close."""
    return (
        status.original_size is not None
        and math.isclose(
            abs(venue.position.size_signed),
            status.original_size,
            rel_tol=0.0,
            abs_tol=QUANTITY_TOLERANCE,
        )
        and not any(fill.oid == status.oid for fill in venue.fills)
    )


def _canceled_fill_size(
    status: HyperliquidOrderStatus, venue: SolReconciliationSnapshot, *, entering: bool
) -> float | None:
    size = venue.position.size_signed
    if status.status != "canceled" or not math.isfinite(size) or size == 0.0:
        return None
    if entering and venue.open_orders:
        return None
    if entering:
        expected = abs(size)
    elif status.original_size is not None:
        expected = status.original_size - abs(size)
    else:
        return None
    filled = owned_fill_quantity(
        venue,
        status.oid,
        position_size_signed=size,
        entering=entering,
        earliest_ms=0,
        latest_ms=status.status_timestamp_ms,
    )
    if (
        expected <= 0.0
        or filled is None
        or not math.isclose(
            filled,
            expected,
            rel_tol=0.0,
            abs_tol=QUANTITY_TOLERANCE,
        )
    ):
        return None
    if status.original_size is not None and filled > status.original_size + QUANTITY_TOLERANCE:
        return None
    return filled
