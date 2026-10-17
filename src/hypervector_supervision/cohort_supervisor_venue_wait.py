"""Read-only view of a backend that is waiting for the venue before its start."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path

# Written next to process.lock by hypervector.live.cohort_venue_start_probe;
# the two names must agree.
VENUE_WAIT_MARKER = "venue_wait.json"
# The backend rewrites the marker on every attempt, at most 300 s apart.
MARKER_FRESH_SECONDS = 900.0


@dataclass(frozen=True)
class VenueWait:
    """One backend's published wait for a reachable venue."""

    pid: int
    waiting_since_utc: str
    attempts: int
    reason: str


def backend_venue_wait(process_lock: Path, pid: int, now: float) -> VenueWait | None:
    """Return the wait that exact backend published, or None when it is not waiting.

    A marker from another process, a stale one or an unreadable one reads as not
    waiting, so the ordinary heartbeat rules apply to it.
    """
    try:
        payload = json.loads(
            process_lock.with_name(VENUE_WAIT_MARKER).read_text(encoding="utf-8")
        )
    except (OSError, ValueError, UnicodeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return None
    marker_pid, attempts = payload.get("pid"), payload.get("attempts")
    since, reason = payload.get("waiting_since_utc"), payload.get("reason")
    if type(marker_pid) is not int or marker_pid != pid:
        return None
    if type(attempts) is not int or attempts < 1:
        return None
    if not isinstance(since, str) or not isinstance(reason, str) or not reason:
        return None
    updated = _timestamp(payload.get("updated_at_utc"))
    if updated is None or abs(now - updated) > MARKER_FRESH_SECONDS:
        return None
    return VenueWait(pid, since, attempts, reason)


def _timestamp(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    stamp = parsed.timestamp()
    return stamp if math.isfinite(stamp) else None
