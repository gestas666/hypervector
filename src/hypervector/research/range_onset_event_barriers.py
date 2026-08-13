"""Chronological adverse and optional favorable barriers for event replay."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from hypervector.research.range_onset_event_models import (
    EventFunding,
    EventReplayConfig,
)
from hypervector.research.range_onset_event_risk import (
    BarrierCrossing,
    EventRiskPosition,
    first_risk_crossing,
)

BarrierExitReason = Literal["liquidation", "stop", "target"]
_BPS_DENOMINATOR = 10_000.0


@dataclass(frozen=True)
class EventBarrierCrossing:
    """First conservatively ordered lifecycle barrier crossing."""

    event_time_ms: int
    reason: BarrierExitReason


def first_barrier_crossing(
    position: EventRiskPosition,
    funding: Sequence[EventFunding],
    config: EventReplayConfig,
    crossing_source: BarrierCrossing,
    end_time_ms: int,
) -> EventBarrierCrossing | None:
    """Return the first target or adverse crossing; adverse wins a tie."""
    adverse = first_risk_crossing(
        position, funding, config, crossing_source, end_time_ms
    )
    target_time = _target_crossing(position, config, crossing_source, end_time_ms)
    if adverse is not None and (
        target_time is None or adverse.event_time_ms <= target_time
    ):
        return EventBarrierCrossing(adverse.event_time_ms, adverse.reason)
    return None if target_time is None else EventBarrierCrossing(target_time, "target")


def _target_crossing(
    position: EventRiskPosition,
    config: EventReplayConfig,
    crossing_source: BarrierCrossing,
    end_time_ms: int,
) -> int | None:
    if config.target_bps is None:
        return None
    fraction = config.target_bps / _BPS_DENOMINATOR
    if position.direction == "long":
        direction = "short"
        target = position.entry_price * (1.0 + fraction)
    else:
        direction = "long"
        target = position.entry_price * (1.0 - fraction)
    return crossing_source(direction, target, position.entry_time_ms, end_time_ms)
