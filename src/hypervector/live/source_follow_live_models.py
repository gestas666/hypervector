"""Lifecycle value objects for the BTC source-follow live engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SourceFollowLiveState(Enum):
    """Venue-reconciled source-follow lifecycle states."""

    FLAT = "FLAT"
    ENTRY_PENDING = "ENTRY_PENDING"
    OPEN_TARGET_RESTING = "OPEN_TARGET_RESTING"
    EXIT_PENDING = "EXIT_PENDING"
    FAULT = "FAULT"


@dataclass(frozen=True)
class SourceFollowLiveSnapshot:
    """Immutable state projected to the ledger and TUI."""

    state: SourceFollowLiveState
    entry_oid: int | None = None
    target_oid: int | None = None
    position_size_signed: float = 0.0
    opened_at_ms: int | None = None
    last_fault: str | None = None
