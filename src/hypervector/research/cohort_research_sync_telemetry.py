"""Durable report-only import state, independent of consumable log records."""

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Literal

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """Return an aware UTC observation time for import telemetry."""
    return datetime.now(timezone.utc)


class ResearchSyncTelemetry:
    """Retain the latest successful import and unresolved failure through retries."""

    def __init__(self, *, enabled: bool = True, clock: Clock = utc_now) -> None:
        """Initialize known configuration without inventing prior import evidence."""
        self._clock = clock
        self._state = "waiting" if enabled else "disabled"
        self._last_attempt: datetime | None = None
        self._last_success: datetime | None = None
        self._last_imported_events: int | None = None
        self._error: str | None = None

    def begin_attempt(self) -> None:
        """Mark a new attempt while retaining any unresolved prior failure."""
        self._last_attempt = self._now()
        self._state = "running"

    def failed(
        self, error: str, *, state: Literal["failed", "deferred"] = "failed"
    ) -> None:
        """Retain the failure until a later import actually succeeds."""
        if not error.strip():
            raise ValueError("research sync failure requires an actionable error")
        self._error = error
        self._state = state

    def succeeded(self, report: Mapping[str, object]) -> None:
        """Record successful completion; an omitted count remains unavailable."""
        count = report.get("imported_events")
        if count is not None and (type(count) is not int or count < 0):
            raise ValueError(
                "research sync imported_events must be a nonnegative integer"
            )
        self._last_success = self._now()
        self._last_imported_events = count
        self._error = None
        self._state = "ready"

    def snapshot(self) -> dict[str, object]:
        """Expose import progress and age without claiming newest-source freshness."""
        now = self._now()
        age = (
            None
            if self._last_success is None
            else (now - self._last_success).total_seconds()
        )
        if age is not None and age < 0:
            raise ValueError(
                "research sync observation clock precedes its last success"
            )
        return {
            "schema_version": 1,
            "execution_authority": "none",
            "state": self._state,
            "in_progress": self._state == "running",
            "last_attempt_at_utc": None
            if self._last_attempt is None
            else self._last_attempt.isoformat(),
            "last_success_at_utc": None
            if self._last_success is None
            else self._last_success.isoformat(),
            "last_success_age_seconds": age,
            "last_imported_events": self._last_imported_events,
            "error": self._error,
        }

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("research sync observation clock must be timezone-aware")
        return value.astimezone(timezone.utc)
