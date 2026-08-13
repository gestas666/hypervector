"""Causal long/short decision arbitration for one shared BTC portfolio."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Literal

import pandas as pd

from hypervector.research.source_follow_portfolio_models import SourceSignal

SharedStrategyId = Literal["source_follow_short", "liquidity_sweep_long"]
_LONG_STOP_MARGIN_PCT = 18.0
_MAXIMUM_HOLD_SECONDS = 86_400.0
_AVAILABILITY_SHIFT = pd.Timedelta(minutes=1)
_REARM_LEAD = pd.Timedelta(seconds=5)


@dataclass(frozen=True)
class SharedEntryEvent:
    """One causally available strategy entry annotation."""

    available_at: pd.Timestamp
    direction: Literal["long", "short"]
    strategy_id: SharedStrategyId
    stop_margin_pct: float | None = None
    maximum_hold_seconds: float = _MAXIMUM_HOLD_SECONDS

    def __post_init__(self) -> None:
        """Reject timestamps and risk annotations outside the frozen contract."""
        if self.available_at.tz is None:
            raise ValueError("shared entry event timestamp must be timezone-aware")
        if self.direction not in {"long", "short"}:
            raise ValueError("shared entry event direction must be long or short")
        stop = self.stop_margin_pct
        if stop is not None and (not math.isfinite(stop) or not 0.0 < stop < 100.0):
            raise ValueError("shared entry stop margin pct must be within (0, 100)")
        if (
            not math.isfinite(self.maximum_hold_seconds)
            or self.maximum_hold_seconds <= 0
        ):
            raise ValueError("shared entry maximum hold must be positive")


@dataclass(frozen=True)
class SharedDecisionGrid:
    """Short, long, and causally arbitrated decision controls."""

    short_control: pd.DataFrame
    long_control: pd.DataFrame
    combined: pd.DataFrame
    short_events: int
    long_events: int
    simultaneous_long_events_dropped: int

    def as_mapping(self) -> dict[str, pd.DataFrame]:
        """Return the three named decision streams for grid replay."""
        return {
            "short_control": self.short_control,
            "long_control": self.long_control,
            "combined": self.combined,
        }


def _validate_window(start: datetime, end: datetime) -> None:
    offsets = (start.utcoffset(), end.utcoffset())
    if any(offset is None or offset.total_seconds() != 0.0 for offset in offsets):
        raise ValueError("shared decision window requires UTC bounds")
    if start >= end:
        raise ValueError("shared decision window must be positive")


def _short_events(
    signals: tuple[SourceSignal, ...], start: datetime, end: datetime
) -> tuple[SharedEntryEvent, ...]:
    events: list[SharedEntryEvent] = []
    for signal in signals:
        if signal.direction != "short":
            raise ValueError("shared short control received a non-short signal")
        timestamp = pd.Timestamp(signal.decision_time_utc)
        if pd.Timestamp(start) <= timestamp < pd.Timestamp(end):
            events.append(SharedEntryEvent(timestamp, "short", "source_follow_short"))
    return tuple(events)


def _long_events(
    decisions: pd.DataFrame, start: datetime, end: datetime
) -> tuple[SharedEntryEvent, ...]:
    if not isinstance(decisions.index, pd.DatetimeIndex) or decisions.index.tz is None:
        raise ValueError("shared long decisions require a timezone-aware index")
    if not decisions.index.is_unique or not decisions.index.is_monotonic_increasing:
        raise ValueError("shared long decisions must be unique and chronological")
    if "entry_direction" not in decisions:
        raise ValueError("shared long decisions require entry_direction")
    available = decisions.index + _AVAILABILITY_SHIFT
    selected = available[decisions["entry_direction"].eq("long")]
    bounded = selected[
        (selected >= pd.Timestamp(start)) & (selected < pd.Timestamp(end))
    ]
    return tuple(
        SharedEntryEvent(
            pd.Timestamp(timestamp),
            "long",
            "liquidity_sweep_long",
            stop_margin_pct=_LONG_STOP_MARGIN_PCT,
        )
        for timestamp in bounded
    )


def _one_shot_decisions(events: tuple[SharedEntryEvent, ...]) -> pd.DataFrame:
    columns = (
        "entry_direction",
        "structural_direction",
        "entry_stop_margin_pct",
        "maximum_hold_seconds",
        "strategy_id",
        "decision_kind",
    )
    rows: list[dict[str, object]] = []
    index: list[pd.Timestamp] = []
    for event in sorted(events, key=lambda item: item.available_at):
        decision_at = event.available_at - _AVAILABILITY_SHIFT
        index.extend((decision_at - _REARM_LEAD, decision_at))
        shared = {"strategy_id": event.strategy_id}
        rows.append(
            {
                **shared,
                "entry_direction": None,
                "structural_direction": None,
                "entry_stop_margin_pct": None,
                "maximum_hold_seconds": None,
                "decision_kind": "shared_rearm",
            }
        )
        rows.append(
            {
                **shared,
                "entry_direction": event.direction,
                "structural_direction": event.direction,
                "entry_stop_margin_pct": event.stop_margin_pct,
                "maximum_hold_seconds": event.maximum_hold_seconds,
                "decision_kind": "shared_entry",
            }
        )
    frame = pd.DataFrame(rows, columns=columns, index=pd.DatetimeIndex(index, tz="UTC"))
    if frame.index.has_duplicates:
        raise ValueError("shared decision rearm windows collide")
    return frame.sort_index(kind="stable")


def build_shared_btc_decision_grid(
    short_signals: tuple[SourceSignal, ...],
    long_decisions: pd.DataFrame,
    *,
    start: datetime,
    end: datetime,
) -> SharedDecisionGrid:
    """Build causal control and combined decisions within one UTC window."""
    _validate_window(start, end)
    shorts = _short_events(short_signals, start, end)
    longs = _long_events(long_decisions, start, end)
    short_times = {event.available_at for event in shorts}
    retained_longs = tuple(
        event for event in longs if event.available_at not in short_times
    )
    return SharedDecisionGrid(
        _one_shot_decisions(shorts),
        _one_shot_decisions(longs),
        _one_shot_decisions(
            tuple(
                sorted((*shorts, *retained_longs), key=lambda event: event.available_at)
            )
        ),
        len(shorts),
        len(longs),
        len(longs) - len(retained_longs),
    )
