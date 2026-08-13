"""Pending and open lifecycle bookkeeping for maker replay."""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal

import pandas as pd

from hypervector.research.maker_replay_models import (
    MakerReplayLifecycle,
    OpenPosition,
    PendingEntry,
    ReplayState,
)


def replace_lifecycle(
    state: ReplayState,
    lifecycle_id: int,
    **changes: object,
) -> None:
    """Replace one immutable lifecycle row inside mutable replay state."""
    current = state.lifecycles[lifecycle_id]
    state.lifecycles[lifecycle_id] = MakerReplayLifecycle(
        **{**asdict(current), **changes}
    )


def resolve_pending(
    state: ReplayState,
    pending: PendingEntry,
    timestamp: pd.Timestamp,
    status: Literal["expired", "canceled"],
) -> None:
    """Record one terminal pending-entry outcome."""
    replace_lifecycle(
        state,
        pending.lifecycle_id,
        outcome_time_utc=timestamp.isoformat(),
        status=status,
    )


def mark_open(state: ReplayState, position: OpenPosition) -> None:
    """Record that a pending lifecycle became an open position."""
    replace_lifecycle(
        state,
        position.lifecycle_id,
        entry_time_utc=position.entry_time.isoformat(),
        status="open",
        entry_price=position.entry_price,
        quantity=position.quantity,
        stop_price=position.stop_price,
    )
