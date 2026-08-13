"""Lifecycle value objects for the Apex MM measurement canary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ApexMMLiveState(Enum):
    """Venue-reconciled market-maker lifecycle states."""

    STARTING = "STARTING"
    QUOTING = "QUOTING"
    INVENTORY = "INVENTORY"
    STOPPED = "STOPPED"
    FAULT = "FAULT"


@dataclass(frozen=True)
class ApexMMLiveSnapshot:
    """Immutable live state projected to the authoritative ledger."""

    state: ApexMMLiveState
    bid_oid: int | None = None
    ask_oid: int | None = None
    position_size_signed: float = 0.0
    quote_started_at_ms: int | None = None
    last_fault: str | None = None
