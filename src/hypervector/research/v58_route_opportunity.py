"""Validated route readiness diagnostics for the V58 observer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isclose, isfinite

Record = Mapping[str, object]


@dataclass(frozen=True)
class RouteOpportunity:
    """One exact V58 route's setup progression and evidence disposition."""

    route: str
    evaluations: int
    eligible: int
    first_fraction: float
    minimum_fraction: float
    mean_fraction: float
    latest_fraction: float
    maximum_fraction: float
    progressions: int
    regressions: int
    state_transitions: int
    unchanged: int
    blocker_counts: dict[str, int]
    reason_counts: dict[str, int]
    latest_reason: str
    latest_side: str | None
    research_state: str
    confidence: str
    eligible_by_side: dict[str, int] | None = None


@dataclass(frozen=True)
class RouteOpportunityCollection:
    """Validated route opportunity matrix and immutable source bytes."""

    opportunities: tuple[RouteOpportunity, ...]
    evidence: dict[str, object]


def parse_route_opportunity(
    route: str, readiness_value: object, score_value: object
) -> RouteOpportunity:
    """Parse one exact checkpoint route without inferring frequency or edge."""
    readiness = _mapping(readiness_value, f"{route} readiness")
    score = _mapping(score_value, f"{route} scorecard")
    evaluations = _count(readiness.get("count"), f"{route} count")
    eligible = _count(readiness.get("eligible"), f"{route} eligible")
    if eligible > evaluations:
        raise ValueError(f"{route} eligible count exceeds evaluations")
    latest_side = readiness.get("latest_side")
    if latest_side not in {None, "long", "short"}:
        raise ValueError(f"{route} latest side is invalid")
    blockers = _count_mapping(readiness.get("blockers"), route, "blockers")
    reasons = _count_mapping(readiness.get("reasons"), route, "reasons")
    _require_count_reconciliation(route, evaluations, blockers, reasons)
    return _opportunity(
        route, readiness, score, evaluations, eligible, latest_side, blockers, reasons
    )


def opportunity_row(item: RouteOpportunity) -> dict[str, object]:
    """Serialize report-only setup cadence without claiming trade frequency."""
    return {
        "route": item.route,
        "evaluations": item.evaluations,
        "eligible": item.eligible,
        "observed_eligible_rate": (
            item.eligible / item.evaluations if item.evaluations else 0.0
        ),
        "readiness_distribution": _readiness_distribution(item),
        "blocker_counts": dict(item.blocker_counts),
        "reason_counts": dict(item.reason_counts),
        "latest_readiness_fraction": item.latest_fraction,
        "maximum_readiness_fraction": item.maximum_fraction,
        "latest_reason": item.latest_reason,
        "latest_side": item.latest_side,
        "eligible_by_side": (
            dict(item.eligible_by_side) if item.eligible_by_side is not None else None
        ),
        "research_state": item.research_state,
        "confidence": item.confidence,
        "readiness_is_edge_claim": False,
        "frequency_claimed": False,
        "automatic_live_change": False,
    }


def require_opportunity_routes(
    collection: RouteOpportunityCollection, routes: Sequence[str]
) -> tuple[RouteOpportunity, ...]:
    """Require one unique diagnostic row for every exact configured route."""
    items = tuple(collection.opportunities)
    expected = set(routes)
    if len(items) != len(expected) or {item.route for item in items} != expected:
        raise ValueError("V58 opportunity route set is incomplete or aliased")
    return items


def _opportunity(
    route: str,
    readiness: Record,
    score: Record,
    evaluations: int,
    eligible: int,
    latest_side: object,
    blockers: dict[str, int],
    reasons: dict[str, int],
) -> RouteOpportunity:
    first, minimum, mean, latest, maximum = _fraction_summary(readiness, route)
    return RouteOpportunity(
        route,
        evaluations,
        eligible,
        first,
        minimum,
        mean,
        latest,
        maximum,
        _count(readiness.get("progressions"), f"{route} progressions"),
        _count(readiness.get("regressions"), f"{route} regressions"),
        _count(readiness.get("state_transitions"), f"{route} state transitions"),
        _count(readiness.get("unchanged"), f"{route} unchanged"),
        blockers,
        reasons,
        _text(readiness.get("latest_reason"), f"{route} reason"),
        latest_side if isinstance(latest_side, str) else None,
        _text(score.get("research_state"), f"{route} research state"),
        _text(score.get("confidence"), f"{route} confidence"),
        _eligible_side_counts(readiness, route, eligible),
    )


def _eligible_side_counts(
    readiness: Record, route: str, eligible: int
) -> dict[str, int] | None:
    value = readiness.get("eligible_by_side")
    if value is None:
        return None
    counts = _count_mapping(value, route, "eligible sides")
    if set(counts) != {"long", "short"} or sum(counts.values()) != eligible:
        raise ValueError(f"{route} eligible side counts must reconcile")
    return counts


def _fraction_summary(readiness: Record, route: str) -> tuple[float, ...]:
    values = tuple(
        _fraction(readiness.get(field), route)
        for field in (
            "first_fraction",
            "minimum_fraction",
            "mean_fraction",
            "latest_fraction",
            "maximum_fraction",
        )
    )
    first, minimum, mean, latest, maximum = values
    if not _inside_distribution(first, minimum, maximum):
        raise ValueError(f"{route} readiness distribution is inconsistent")
    if not _inside_distribution(mean, minimum, maximum):
        raise ValueError(f"{route} readiness distribution is inconsistent")
    if not _inside_distribution(latest, minimum, maximum):
        raise ValueError(f"{route} readiness distribution is inconsistent")
    return values


def _inside_distribution(value: float, minimum: float, maximum: float) -> bool:
    above = value >= minimum or isclose(value, minimum, rel_tol=0.0, abs_tol=1e-12)
    below = value <= maximum or isclose(value, maximum, rel_tol=0.0, abs_tol=1e-12)
    return above and below


def _readiness_distribution(item: RouteOpportunity) -> dict[str, object]:
    return {
        "first_fraction": item.first_fraction,
        "minimum_fraction": item.minimum_fraction,
        "mean_fraction": item.mean_fraction,
        "maximum_fraction": item.maximum_fraction,
        "progressions": item.progressions,
        "regressions": item.regressions,
        "state_transitions": item.state_transitions,
        "unchanged": item.unchanged,
    }


def _require_count_reconciliation(
    route: str,
    evaluations: int,
    blockers: Mapping[str, int],
    reasons: Mapping[str, int],
) -> None:
    if sum(reasons.values()) != evaluations:
        raise ValueError(f"{route} reason counts must reconcile to evaluations")
    if any(count > evaluations for count in blockers.values()):
        raise ValueError(f"{route} blocker count exceeds evaluations")


def _count_mapping(value: object, route: str, label: str) -> dict[str, int]:
    rows = _mapping(value, f"{route} {label}")
    return {
        _text(key, f"{route} {label} name"): _count(count, f"{route} count")
        for key, count in rows.items()
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _fraction(value: object, route: str) -> float:
    valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not valid or not isfinite(value) or not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{route} readiness fraction must be within zero and one")
    return float(value)
