"""Strict target-order projection for one open cohort lifecycle."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.research.cohort_live_audit_values import mapping, number, positive_int

Record = Mapping[str, object]


def project_open_target_order(position: Record, side: str) -> dict[str, object] | None:
    """Return an exact active target and its backend-computed distance."""
    value = position.get("target_order")
    if value is None:
        return None
    target = mapping(value, "open trade target order")
    oid = positive_int(target.get("oid"), "open trade target oid")
    limit_price = number(target.get("limit_price"), "open trade target price")
    mark_price = number(position.get("mark_price"), "open trade mark price")
    if limit_price <= 0.0 or mark_price <= 0.0:
        raise ValueError("open trade target and mark prices must be positive")
    if side not in {"long", "short"}:
        raise ValueError("open trade target side must be long or short")
    direction = 1.0 if side == "long" else -1.0
    return {
        "oid": oid,
        "limit_price": limit_price,
        "directional_distance_bps": (limit_price / mark_price - 1.0)
        * direction
        * 10_000.0,
    }
