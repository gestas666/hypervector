"""Exact bracket matching and restart-state recovery for Hulk."""

from __future__ import annotations

from collections.abc import Mapping
import math

from hypervector.live.hulk_smash_live_models import (
    HulkSmashLiveSnapshot,
    HulkSmashLiveState,
)
from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot


class HulkSmashRestartError(RuntimeError):
    """Prior Hulk ownership cannot be matched exactly to venue state."""


def has_stop(venue: SolReconciliationSnapshot, oid: int) -> bool:
    """Report whether the exact reduce-only trigger is venue-visible."""
    position_size = abs(venue.position.size_signed)
    return any(
        order.oid == oid
        and order.side == "B"
        and order.reduce_only
        and order.is_trigger
        and order.size >= position_size
        for order in venue.open_orders
    )


def has_bracket(
    venue: SolReconciliationSnapshot,
    stop_oid: int,
    target_oid: int,
) -> bool:
    """Report whether both exact reduce-only bracket legs are visible."""
    stop = next((order for order in venue.open_orders if order.oid == stop_oid), None)
    target = next(
        (order for order in venue.open_orders if order.oid == target_oid), None
    )
    return bool(
        stop
        and target
        and stop.side == "B"
        and target.side == "B"
        and stop.reduce_only
        and stop.is_trigger
        and target.reduce_only
        and not target.is_trigger
        and stop.size >= abs(venue.position.size_signed)
        and target.size >= abs(venue.position.size_signed)
    )


def restore_hulk_snapshot(
    records: list[dict[str, object]],
    *,
    profile_fingerprint: str,
    venue: SolReconciliationSnapshot,
) -> HulkSmashLiveSnapshot:
    """Restore only the latest exact OPEN identity and two owned orders."""
    restored = restore_hulk_owned_snapshot(records, profile_fingerprint)
    if restored is None:
        raise HulkSmashRestartError("unowned BTC exposure at Hulk startup")
    if not _bracket_matches_snapshot(venue, restored):
        raise HulkSmashRestartError("owned restart bracket does not match venue")
    if len(venue.open_orders) != 2:
        raise HulkSmashRestartError(
            "restart venue contains orders outside owned bracket"
        )
    return HulkSmashLiveSnapshot(
        state=HulkSmashLiveState.OPEN,
        entry_oid=restored.entry_oid,
        stop_oid=restored.stop_oid,
        target_oid=restored.target_oid,
        position_size_signed=venue.position.size_signed,
        opened_at_ms=restored.opened_at_ms,
        entry_price=venue.position.entry_price,
        stop_price=restored.stop_price,
        target_price=restored.target_price,
    )


def restore_hulk_owned_snapshot(
    records: list[dict[str, object]],
    profile_fingerprint: str,
) -> HulkSmashLiveSnapshot | None:
    """Return the latest durable open ownership, including a stopped bracket."""
    payload = _latest_owned_state(records, profile_fingerprint)
    if payload is None:
        return None
    if payload.get("state") == "STOPPED" and _is_flat_payload(payload):
        return None
    return _snapshot_from_payload(payload)


def _latest_owned_state(
    records: list[dict[str, object]], profile_fingerprint: str
) -> Mapping[str, object] | None:
    for record in reversed(records):
        if record.get("event_type") != "state_transition":
            continue
        if record.get("profile_fingerprint") != profile_fingerprint:
            return None
        payload = record.get("payload")
        if not isinstance(payload, dict) or payload.get("state") not in {
            "OPEN",
            "STOPPED",
        }:
            return None
        return payload
    return None


def _bracket_matches_snapshot(
    venue: SolReconciliationSnapshot,
    snapshot: HulkSmashLiveSnapshot,
) -> bool:
    if not has_bracket(venue, snapshot.stop_oid or 0, snapshot.target_oid or 0):
        return False
    stop = next(order for order in venue.open_orders if order.oid == snapshot.stop_oid)
    target = next(
        order for order in venue.open_orders if order.oid == snapshot.target_oid
    )
    return bool(
        stop.trigger_price is not None
        and target.limit_price is not None
        and snapshot.stop_price is not None
        and snapshot.target_price is not None
        and math.isclose(stop.trigger_price, snapshot.stop_price)
        and math.isclose(target.limit_price, snapshot.target_price)
    )


def _snapshot_from_payload(payload: Mapping[str, object]) -> HulkSmashLiveSnapshot:
    return HulkSmashLiveSnapshot(
        state=HulkSmashLiveState.OPEN,
        entry_oid=_positive_integer(payload.get("entry_oid"), "entry_oid"),
        stop_oid=_positive_integer(payload.get("stop_oid"), "stop_oid"),
        target_oid=_positive_integer(payload.get("target_oid"), "target_oid"),
        position_size_signed=_negative_number(
            payload.get("position_size_signed"), "position_size_signed"
        ),
        opened_at_ms=_nonnegative_integer(payload.get("opened_at_ms"), "opened_at_ms"),
        entry_price=_positive_number(payload.get("entry_price"), "entry_price"),
        stop_price=_positive_number(payload.get("stop_price"), "stop_price"),
        target_price=_positive_number(payload.get("target_price"), "target_price"),
    )


def _is_flat_payload(payload: Mapping[str, object]) -> bool:
    value = payload.get("position_size_signed")
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) == 0.0
    )


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HulkSmashRestartError(f"restart {label} must be a positive integer")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HulkSmashRestartError(f"restart {label} must be nonnegative")
    return value


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HulkSmashRestartError(f"restart {label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise HulkSmashRestartError(f"restart {label} must be positive")
    return number


def _negative_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HulkSmashRestartError(f"restart {label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number >= 0.0:
        raise HulkSmashRestartError(f"restart {label} must be negative")
    return number
