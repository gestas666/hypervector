"""Official funding evidence for report-only eligible-policy paths."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class EligiblePolicyFundingEvent:
    """One official Hyperliquid funding settlement rate."""

    timestamp_ms: int
    funding_rate: float

    def __post_init__(self) -> None:
        """Reject invalid settlement timestamps and rates."""
        if isinstance(self.timestamp_ms, bool) or self.timestamp_ms < 0:
            raise ValueError("funding event timestamp must be nonnegative")
        if not isfinite(self.funding_rate):
            raise ValueError("funding event rate must be finite")


@dataclass(frozen=True)
class EligiblePolicyFundingEvidence:
    """Bound one complete official funding-history response window."""

    symbol: str
    requested_start_ms: int
    requested_end_ms: int
    events: tuple[EligiblePolicyFundingEvent, ...]

    def __post_init__(self) -> None:
        """Validate identity, bounds, ordering, and event uniqueness."""
        if not self.symbol.strip():
            raise ValueError("funding evidence symbol must be non-empty")
        if (
            isinstance(self.requested_start_ms, bool)
            or isinstance(self.requested_end_ms, bool)
            or self.requested_start_ms < 0
            or self.requested_end_ms < self.requested_start_ms
        ):
            raise ValueError("funding evidence bounds are invalid")
        times = tuple(event.timestamp_ms for event in self.events)
        if times != tuple(sorted(times)) or len(times) != len(set(times)):
            raise ValueError("funding events must be ordered and unique")
        if any(
            value < self.requested_start_ms or value > self.requested_end_ms
            for value in times
        ):
            raise ValueError("funding event falls outside requested bounds")


def covered_funding_bps(
    evidence: EligiblePolicyFundingEvidence | None,
    *,
    symbol: str,
    side: str,
    start_ms: int,
    end_ms: int,
) -> float | None:
    """Return signed funding bps only when the full path is covered."""
    if evidence is None:
        return None
    if evidence.symbol != symbol:
        raise ValueError("funding evidence symbol does not match candidate")
    if side not in {"long", "short"}:
        raise ValueError("funding direction must be long or short")
    if evidence.requested_start_ms > start_ms or evidence.requested_end_ms < end_ms:
        return None
    direction = 1.0 if side == "long" else -1.0
    rate = sum(
        event.funding_rate
        for event in evidence.events
        if start_ms < event.timestamp_ms <= end_ms
    )
    return -direction * rate * 10_000.0


def exact_depth_funding_bounds(report: Mapping[str, object]) -> tuple[int, int] | None:
    """Return complete funding bounds for entered exact-depth lifecycles."""
    rows = [
        row
        for field in ("latest_attempts", "latest_executions")
        for row in _report_rows(report.get(field), field)
        if row.get("entry_time_ms") is not None
    ]
    if not rows:
        return None
    starts = [_report_time(row.get("entry_time_ms"), "entry time") for row in rows]
    ends = [_report_end_time(row) for row in rows]
    return min(starts), max(ends)


def parse_official_funding_history(
    rows: Sequence[Mapping[str, object]],
    *,
    symbol: str,
    requested_start_ms: int,
    requested_end_ms: int,
) -> EligiblePolicyFundingEvidence:
    """Parse one successful Hyperliquid ``fundingHistory`` response."""
    events: list[EligiblePolicyFundingEvent] = []
    for row in rows:
        if row.get("coin") != symbol:
            raise ValueError("official funding row coin does not match request")
        timestamp = row.get("time")
        if type(timestamp) is not int:
            raise ValueError("official funding row time must be an integer")
        rate = _finite_float(row.get("fundingRate"), "official funding rate")
        events.append(EligiblePolicyFundingEvent(timestamp, rate))
    return EligiblePolicyFundingEvidence(
        symbol=symbol,
        requested_start_ms=requested_start_ms,
        requested_end_ms=requested_end_ms,
        events=tuple(sorted(events, key=lambda event: event.timestamp_ms)),
    )


def _report_rows(value: object, label: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    if not all(isinstance(row, Mapping) for row in value):
        raise ValueError(f"{label} rows must be mappings")
    return tuple(row for row in value if isinstance(row, Mapping))


def _report_end_time(row: Mapping[str, object]) -> int:
    for field in ("exit_time_ms", "current_exit_time_ms", "deadline_time_ms"):
        if row.get(field) is not None:
            return _report_time(row.get(field), field)
    raise ValueError("entered exact-depth lifecycle has no terminal observation time")


def _report_time(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result
