"""Pure lifecycle checks for Hulk venue snapshots."""

from __future__ import annotations

from hypervector.live.hulk_smash_live_models import HulkSmashLiveSnapshot
from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot


class HulkSmashLiveCheckError(RuntimeError):
    """A venue snapshot violates the owned Hulk lifecycle contract."""


def validate_short_position(
    venue: SolReconciliationSnapshot,
    *,
    leverage: int,
) -> None:
    """Require flat or an isolated short at the configured leverage."""
    position = venue.position
    if position.size_signed > 0.0:
        raise HulkSmashLiveCheckError("Hulk canary refuses BTC long exposure")
    if position.size_signed < 0.0 and (
        position.leverage_type != "isolated" or position.leverage != leverage
    ):
        raise HulkSmashLiveCheckError(f"BTC exposure must be isolated at {leverage}x")


def filled_exit_reason(
    snapshot: HulkSmashLiveSnapshot,
    venue: SolReconciliationSnapshot,
) -> str:
    """Attribute a flat venue to one exact owned exit fill."""
    fill_oids = {fill.oid for fill in venue.fills}
    target_filled = snapshot.target_oid is not None and snapshot.target_oid in fill_oids
    stop_filled = snapshot.stop_oid is not None and snapshot.stop_oid in fill_oids
    if target_filled and stop_filled:
        return "mixed_bracket_exit"
    if target_filled:
        return "target"
    if stop_filled:
        return "protective_stop"
    raise HulkSmashLiveCheckError("venue is flat without an owned exit fill")


def filled_oid(
    snapshot: HulkSmashLiveSnapshot,
    venue: SolReconciliationSnapshot,
) -> int | None:
    """Return the uniquely latest owned bracket fill ID when observable."""
    owned_oids = {snapshot.target_oid, snapshot.stop_oid} - {None}
    owned_fills = [fill for fill in venue.fills if fill.oid in owned_oids]
    if not owned_fills:
        return None
    latest_timestamp = max(fill.timestamp_ms for fill in owned_fills)
    latest_oids = {
        fill.oid for fill in owned_fills if fill.timestamp_ms == latest_timestamp
    }
    if len(latest_oids) != 1:
        return None
    return next(iter(latest_oids))


def maximum_hold_reached(
    snapshot: HulkSmashLiveSnapshot,
    *,
    now_ms: int,
    maximum_hold_seconds: int,
) -> bool:
    """Compare durable open time with the configured wall-clock bound."""
    if snapshot.opened_at_ms is None:
        raise HulkSmashLiveCheckError("OPEN state lacks opened_at_ms")
    return now_ms - snapshot.opened_at_ms >= maximum_hold_seconds * 1_000
