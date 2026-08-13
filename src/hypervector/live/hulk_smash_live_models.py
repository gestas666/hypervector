"""Immutable lifecycle models for the Hulk Smash BTC canary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HulkSmashLiveState(Enum):
    """Venue-reconciled states for one protected BTC position."""

    DISARMED = "DISARMED"
    PREFLIGHT = "PREFLIGHT"
    FLAT = "FLAT"
    ENTRY_PENDING = "ENTRY_PENDING"
    PROTECTING = "PROTECTING"
    OPEN = "OPEN"
    EXIT_PENDING = "EXIT_PENDING"
    FAULTED = "FAULTED"
    STOPPED = "STOPPED"


@dataclass(frozen=True)
class HulkSmashLiveSnapshot:
    """Complete durable ownership and price identity for one lifecycle."""

    state: HulkSmashLiveState = HulkSmashLiveState.DISARMED
    entry_oid: int | None = None
    stop_oid: int | None = None
    target_oid: int | None = None
    position_size_signed: float = 0.0
    opened_at_ms: int | None = None
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    last_fault: str | None = None

    def as_payload(self) -> dict[str, object]:
        """Return the recoverable lifecycle state for the append-only ledger."""
        return {
            "state": self.state.value,
            "entry_oid": self.entry_oid,
            "stop_oid": self.stop_oid,
            "target_oid": self.target_oid,
            "position_size_signed": self.position_size_signed,
            "opened_at_ms": self.opened_at_ms,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "last_fault": self.last_fault,
        }
