"""Read-only venue protection and cleanup checks for V58 BRENTOIL."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isclose, isfinite

Record = Mapping[str, object]

_SYMBOL = "xyz:BRENTOIL"


def brentoil_venue_asset(
    venue: Record, *, profile_id: object, profile_fingerprint: object
) -> Record:
    """Return the exact mainnet BRENTOIL asset from authority-none evidence."""
    authority = _mapping(venue.get("authority"), "venue authority")
    if (
        authority.get("execution_authority") != "none"
        or authority.get("execution_client_constructed") is not False
    ):
        raise ValueError("V58 BRENTOIL venue evidence has execution authority")
    identity = _mapping(venue.get("identity"), "venue identity")
    expected = {
        "active_profile_id": profile_id,
        "active_profile_fingerprint": profile_fingerprint,
        "network": "mainnet",
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 BRENTOIL venue identity differs")
    matches = [
        row
        for row in _records(venue.get("assets"), "venue assets")
        if row.get("symbol") == _SYMBOL
    ]
    if len(matches) != 1:
        raise ValueError("V58 BRENTOIL venue coverage differs")
    return matches[0]


def require_brentoil_open_venue(
    venue: Record, *, entry_size: object, protective_stop_oid: object
) -> None:
    """Require the exact open size and one full reduce-only protective stop."""
    position = _mapping(venue.get("position"), "venue position")
    if not _same_number(position.get("size_signed"), entry_size):
        raise ValueError("V58 BRENTOIL venue position differs")
    orders = _records(venue.get("open_orders"), "venue orders")
    if len(orders) != 1:
        raise ValueError("V58 BRENTOIL venue stop coverage differs")
    order = orders[0]
    stop_matches = (
        order.get("oid") == protective_stop_oid
        and order.get("reduce_only") is True
        and _same_number(order.get("size"), entry_size)
    )
    protection = _mapping(venue.get("protection"), "venue protection")
    if not stop_matches or protection.get("full_reduce_only_stop_coverage") is not True:
        raise ValueError("V58 BRENTOIL venue stop coverage differs")
    _require_venue_reconciliation(venue, [protective_stop_oid])


def require_brentoil_flat_venue(venue: Record) -> dict[str, object]:
    """Require a flat position, no orders, and exact ledger reconciliation."""
    position = _mapping(venue.get("position"), "venue position")
    if _number(position.get("size_signed"), "venue flat size") != 0.0:
        raise ValueError("V58 BRENTOIL venue cleanup is not flat")
    if _records(venue.get("open_orders"), "venue orders"):
        raise ValueError("V58 BRENTOIL venue cleanup retains orders")
    _require_venue_reconciliation(venue, [])
    return {"venue_flat_order_free": True, "venue_ledger_reconciled": True}


def _require_venue_reconciliation(venue: Record, order_ids: list[object]) -> None:
    ledger = _mapping(venue.get("ledger_reconciliation"), "venue reconciliation")
    for key in ("matches", "orders_match", "position_matches"):
        if ledger.get(key) is not True:
            raise ValueError("V58 BRENTOIL venue ledger reconciliation differs")
    if ledger.get("venue_owned_order_ids") != order_ids:
        raise ValueError("V58 BRENTOIL venue owned orders differ")


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"V58 BRENTOIL {label} must be a list")
    return tuple(_mapping(row, label) for row in value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 BRENTOIL {label} must be a mapping")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 BRENTOIL {label} must be numeric")
    output = float(value)
    if not isfinite(output):
        raise ValueError(f"V58 BRENTOIL {label} must be finite")
    return output


def _same_number(left: object, right: object) -> bool:
    return isclose(
        _number(left, "numeric identity"),
        _number(right, "numeric identity"),
        abs_tol=1e-10,
    )
