"""Prospective boundary validation for exact-route lifecycle evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import math

from hypervector.research.cohort_route_lifecycle_values import count, mapping

Record = Mapping[str, object]


@dataclass(frozen=True)
class RouteLifecycleBoundary:
    """Frozen prospective start and cumulative readiness baseline."""

    capture_start_ms: int
    baseline_evaluations: int
    baseline_eligible: int

    def __post_init__(self) -> None:
        """Reject invalid or internally inconsistent baselines."""
        values = (
            self.capture_start_ms,
            self.baseline_evaluations,
            self.baseline_eligible,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) for value in values
        ):
            raise ValueError("route lifecycle boundary values must be integers")
        if self.capture_start_ms <= 0 or min(values[1:]) < 0:
            raise ValueError("route lifecycle boundary values are out of range")
        if self.baseline_eligible > self.baseline_evaluations:
            raise ValueError("baseline eligible exceeds baseline evaluations")


def prospective_readiness(
    route: Record, boundary: RouteLifecycleBoundary
) -> dict[str, int]:
    """Subtract the frozen cumulative readiness baseline without underflow."""
    evaluations = count(route.get("count"), "route evaluation count")
    eligible = count(route.get("eligible"), "route eligible evaluations")
    if evaluations < boundary.baseline_evaluations:
        raise ValueError("route evaluations regressed behind the frozen baseline")
    if eligible < boundary.baseline_eligible:
        raise ValueError("eligible evaluations regressed behind the frozen baseline")
    return {
        "count": evaluations,
        "eligible": eligible,
        "prospective_evaluations": evaluations - boundary.baseline_evaluations,
        "prospective_eligible": eligible - boundary.baseline_eligible,
    }


def decision_is_prospective(row: Record, capture_start_ms: int) -> bool:
    """Accept a lifecycle only when its attributed decision follows activation."""
    context = mapping(row.get("entry_context"), "entry context")
    signal = mapping(context.get("signal_provider"), "entry signal")
    decision_time_ms = count(
        signal.get("decision_time_ms"), "entry signal decision time"
    )
    return decision_time_ms >= capture_start_ms


def validate_freshness(
    generated_at: datetime,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> None:
    """Reject future, stale, or invalid checkpoint observation times."""
    if observed_at.tzinfo is None:
        raise ValueError("observation time needs a timezone")
    if not math.isfinite(maximum_age_seconds) or maximum_age_seconds <= 0.0:
        raise ValueError("maximum checkpoint age must be finite and positive")
    age = (observed_at.astimezone(UTC) - generated_at).total_seconds()
    if age < 0.0:
        raise ValueError("checkpoint is from the future")
    if age > maximum_age_seconds:
        raise ValueError("checkpoint is stale for route lifecycle evidence")
