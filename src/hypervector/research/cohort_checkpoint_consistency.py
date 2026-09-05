"""Cross-section consistency checks for live cohort checkpoints."""

from __future__ import annotations

from collections.abc import Mapping
import math

Record = Mapping[str, object]


def require_checkpoint_asset_state_consistency(
    lifecycle: Record,
    audit: Record,
) -> None:
    """Reject incompatible lifecycle and venue state across the audit cutoff."""
    lifecycle_states = _mapping(lifecycle.get("asset_states"), "lifecycle states")
    health = _mapping(audit.get("health"), "audit health")
    assets = _mapping(health.get("assets"), "audit asset health")
    audit_states = {
        symbol: _text(_mapping(value, f"{symbol} health").get("final_state"), symbol)
        for symbol, value in assets.items()
    }
    if dict(lifecycle_states) != audit_states and not _clean_post_snapshot_stop(
        lifecycle_states, assets
    ):
        raise ValueError("checkpoint asset state cutoff mismatch")


def _clean_post_snapshot_stop(
    lifecycle_states: Record,
    assets: Record,
) -> bool:
    if not lifecycle_states or set(lifecycle_states) != set(assets):
        return False
    if any(state != "STOPPED" for state in lifecycle_states.values()):
        return False
    for symbol, value in assets.items():
        health = _mapping(value, f"{symbol} health")
        if not _safe_stopped_asset(health):
            return False
    return True


def _safe_stopped_asset(health: Record) -> bool:
    state = health.get("final_state")
    size = health.get("position_size_signed")
    orders = health.get("open_order_ids")
    if (
        isinstance(size, bool)
        or not isinstance(size, (int, float))
        or not math.isfinite(float(size))
        or not isinstance(orders, list)
    ):
        return False
    if state == "FLAT":
        return float(size) == 0.0 and not orders
    stop_oid = health.get("stop_oid")
    return (
        state == "OPEN"
        and float(size) != 0.0
        and health.get("protected_if_open") is True
        and isinstance(stop_oid, int)
        and not isinstance(stop_oid, bool)
        and stop_oid > 0
        and stop_oid in orders
    )


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
