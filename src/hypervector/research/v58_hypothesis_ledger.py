"""Complete experiment-ledger projection for every configured V58 route."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.v58_route_opportunity import RouteOpportunity

Record = Mapping[str, object]


def complete_hypothesis_ledger(
    lifecycle_rows: Sequence[Record], routes: Sequence[RouteOpportunity]
) -> list[dict[str, object]]:
    """Join watcher evidence to all active route experiments without promotion."""
    watched = {str(row.get("route")): row for row in lifecycle_rows}
    if len(watched) != len(lifecycle_rows):
        raise ValueError("V58 hypothesis lifecycle routes are duplicated")
    expected = {route.route for route in routes}
    if not set(watched).issubset(expected):
        raise ValueError("V58 hypothesis lifecycle route is not configured")
    return [_hypothesis_row(watched.get(route.route), route) for route in routes]


def _hypothesis_row(
    lifecycle: Record | None, route: RouteOpportunity
) -> dict[str, object]:
    if lifecycle is not None:
        return {
            **dict(lifecycle),
            "status": "being_tested",
            "evidence_state": lifecycle.get("status"),
            "research_state": route.research_state,
            "confidence": route.confidence,
        }
    return {
        "route": route.route,
        "symbol": _route_symbol(route.route),
        "status": "being_tested",
        "evidence_state": "awaiting_first_eligible_signal",
        "watch_state": "watcher_not_attached",
        "pending_lifecycles": 0,
        "resolved_lifecycles": 0,
        "technical_complete": None,
        "source_age_seconds": None,
        "research_state": route.research_state,
        "confidence": route.confidence,
        "automatic_live_change": False,
    }


def _route_symbol(route: str) -> str:
    parts = route.rsplit("|", maxsplit=1)
    if len(parts) != 2 or not parts[1]:
        raise ValueError("V58 hypothesis route symbol is invalid")
    return parts[1]
