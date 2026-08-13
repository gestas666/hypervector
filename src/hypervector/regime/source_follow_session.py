"""Minute-feed bridge for the pinned source-follow regime runtime."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from hypervector.regime.source_follow_runtime import (
    FiveMinuteBarAssembler,
    SourceFollowDecision,
    SourceFollowRuntime,
)


class SourceFollowSessionSignal:
    """Advance causal 5m source state from completed 1m backend bars."""

    def __init__(
        self,
        runtime: SourceFollowRuntime,
        *,
        entry_session_utc: str = "24/7",
    ) -> None:
        self._runtime = runtime
        self._assembler = FiveMinuteBarAssembler()
        self._latest_decision: SourceFollowDecision | None = None
        self._entry_session_bounds = _entry_session_bounds(entry_session_utc)

    @classmethod
    def from_pinned_backend(
        cls,
        backend_root: Path | str,
        *,
        minimum_confidence: float = 0.70,
        minimum_range_bps: float = 0.0,
        maximum_range_bps: float = 100.0,
        maximum_hold_seconds: float = 86_400.0,
        entry_pulse_seconds: float = 60.0,
        entry_session_utc: str = "24/7",
    ) -> SourceFollowSessionSignal:
        """Construct a session signal from the checksum-verified source tree."""
        from hypervector.regime.pinned_hypertrader import PinnedHypertraderClassifier

        runtime = SourceFollowRuntime(
            PinnedHypertraderClassifier(backend_root),
            minimum_confidence=minimum_confidence,
            minimum_range_bps=minimum_range_bps,
            maximum_range_bps=maximum_range_bps,
            maximum_hold_seconds=maximum_hold_seconds,
            entry_pulse_seconds=entry_pulse_seconds,
        )
        return cls(runtime, entry_session_utc=entry_session_utc)

    @property
    def latest_decision(self) -> SourceFollowDecision | None:
        """Return the most recent completed 5m source decision, if available."""
        return self._latest_decision

    def update_minute(
        self,
        *,
        timestamp_utc: datetime,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> SourceFollowDecision | None:
        """Consume one completed 1m bar without extrapolating incomplete state."""
        bar = self._assembler.update(
            timestamp_utc=timestamp_utc,
            open=open,
            high=high,
            low=low,
            close=close,
            volume=volume,
        )
        if bar is not None:
            self._latest_decision = self._runtime.update(bar)
        return self._latest_decision

    def directions_at(self, observed_at: datetime) -> tuple[str | None, str | None]:
        """Return the entry and cancellation-authority pulse at one UTC time."""
        if not self.entry_session_active_at(observed_at):
            return None, None
        direction = self._runtime.entry_direction_at(observed_at)
        return direction, direction

    def entry_session_active_at(self, observed_at: datetime) -> bool:
        """Return whether new entries are allowed at a timezone-aware UTC time."""
        if observed_at.tzinfo is None or observed_at.utcoffset() != timedelta(0):
            raise ValueError("entry session observation timestamp must be UTC")
        if self._entry_session_bounds is None:
            return True
        minute = observed_at.hour * 60 + observed_at.minute
        start, end = self._entry_session_bounds
        return start <= minute < end


def _entry_session_bounds(value: str) -> tuple[int, int] | None:
    if value == "24/7":
        return None
    if value == "[06:00,15:00)":
        return 6 * 60, 15 * 60
    raise ValueError(f"unsupported source-follow entry session: {value!r}")
