"""Execution-scope-aware lifecycle capture priorities for exact V58."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite

from hypervector.research.v58_route_opportunity import RouteOpportunity

_EXECUTABLE_SIDES = {
    "hulk_expansion_short_robust_v3|BTC": frozenset({"short"}),
    "hulk_expansion_short_tuned_v2|BTC": frozenset({"short"}),
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC": frozenset({"long"}),
    "eth_breakout_precompression_pullback_bidirectional_v1|ETH": frozenset(
        {"long", "short"}
    ),
    "hulk_expansion_bidirectional_tuned_v2|SOL": frozenset({"short"}),
    "hype_breakout_compression_alignment_bidirectional_v2|HYPE": frozenset(
        {"long", "short"}
    ),
    "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500": (
        frozenset({"long", "short"})
    ),
    "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX": frozenset(
        {"short"}
    ),
    "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:SNDK": (
        frozenset({"short"})
    ),
    "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:BRENTOIL": (
        frozenset({"long", "short"})
    ),
}


def highest_value_investigation(
    items: Sequence[object],
    routes: Sequence[RouteOpportunity],
    *,
    reviewed_routes: frozenset[str] = frozenset(),
    live_open_lifecycles: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Rank resolved, executable-unwatched, open, then unresolved-side evidence."""
    item_routes = {str(getattr(item, "route")) for item in items}
    if not reviewed_routes.issubset(item_routes):
        raise ValueError("V58 reviewed route is not lifecycle-bound")
    live = _open_lifecycle_investigation(live_open_lifecycles)
    if live is not None:
        return live
    for item in items:
        if getattr(item, "resolved") and getattr(item, "route") not in reviewed_routes:
            return _investigation(
                getattr(item, "route"),
                "review_resolved_exact_lifecycle",
                "new source-compatible lifecycle evidence is complete",
            )
    watched = {str(getattr(item, "route")) for item in items}
    for route in routes:
        if _eligibility_scope(route) == "executable" and route.route not in watched:
            return _investigation(
                route.route,
                "attach_exact_lifecycle_capture",
                "an executable eligible signal has no exact lifecycle watcher",
            )
    for item in items:
        if getattr(item, "pending") and getattr(item, "technical_complete"):
            return _investigation(
                getattr(item, "route"),
                "resolve_open_exact_lifecycle",
                "one source-compatible lifecycle is open under frozen exits",
            )
    for route in routes:
        if _eligibility_scope(route) == "unresolved":
            return _investigation(
                route.route,
                "attribute_eligible_signal_sides",
                "eligible observer events lack exact executable-side attribution",
            )
    return _investigation(
        "hype_breakout_compression_alignment_bidirectional_v2|HYPE",
        "collect_both_side_exact_lifecycles",
        "the highest-ranked retained route still has no exact V58 outcome",
    )


def _open_lifecycle_investigation(
    value: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if not value:
        return None
    rows = value.get("trades")
    count = value.get("open_lifecycles")
    safe = (
        value.get("execution_authority") == "none"
        and value.get("actual_exit_fills_claimed") is False
        and isinstance(count, int)
        and not isinstance(count, bool)
        and isinstance(rows, Sequence)
        and not isinstance(rows, (str, bytes))
        and count == len(rows)
    )
    if not safe:
        raise ValueError("V58 open-lifecycle investigation source is invalid")
    candidates = [_open_candidate(row) for row in rows]
    if not candidates:
        return None
    giveback, lifecycle, route = max(candidates, key=lambda item: item[0])
    return {
        **_investigation(
            route,
            "reconcile_open_live_lifecycle",
            "actual live capital is open under a frozen exit contract",
        ),
        "lifecycle_id": lifecycle,
        "priority_basis": "largest_marked_to_stop_giveback_usd",
        "marked_to_stop_giveback_usd": giveback,
    }


def _open_candidate(value: object) -> tuple[float, str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("V58 open-lifecycle investigation row is invalid")
    lifecycle = value.get("lifecycle_id")
    strategy = value.get("strategy_id")
    symbol = value.get("symbol")
    protection = value.get("profit_protection_estimate")
    if not all(
        isinstance(item, str) and item for item in (lifecycle, strategy, symbol)
    ):
        raise ValueError("V58 open-lifecycle investigation identity is invalid")
    if not isinstance(protection, Mapping):
        raise ValueError("V58 open-lifecycle profit protection is invalid")
    giveback = protection.get("marked_to_stop_giveback_usd")
    if isinstance(giveback, bool) or not isinstance(giveback, (int, float)):
        raise ValueError("V58 open-lifecycle giveback must be numeric")
    output = float(giveback)
    if not isfinite(output) or output < 0.0:
        raise ValueError("V58 open-lifecycle giveback must be nonnegative")
    return output, str(lifecycle), f"{strategy}|{symbol}"


def lifecycle_capture_coverage(
    items: Sequence[object], routes: Sequence[RouteOpportunity]
) -> dict[str, object]:
    """Report capture coverage without treating observe-only signals as entries."""
    watched = {str(getattr(item, "route")) for item in items}
    rows = [_capture_row(route, watched) for route in routes]
    missing = sum(
        row["status"] == "eligible_without_exact_lifecycle_capture" for row in rows
    )
    return {
        "route_count": len(rows),
        "watcher_count": len(watched),
        "eligible_without_exact_capture": missing,
        "routes": rows,
        "execution_authority": "none",
        "automatic_live_change": False,
    }


def _capture_row(route: RouteOpportunity, watched: set[str]) -> dict[str, object]:
    return {
        "route": route.route,
        "eligible_evaluations": route.eligible,
        "watcher_attached": route.route in watched,
        "status": _capture_status(route, watched),
    }


def _capture_status(route: RouteOpportunity, watched: set[str]) -> str:
    if route.route in watched:
        return "exact_lifecycle_watcher_attached"
    scope = _eligibility_scope(route)
    if scope == "executable":
        return "eligible_without_exact_lifecycle_capture"
    if scope == "observe_only":
        return "observe_only_eligible_without_live_authority"
    if scope == "unresolved":
        return "eligible_execution_side_attribution_unavailable"
    return "awaiting_first_eligible_signal"


def _eligibility_scope(route: RouteOpportunity) -> str:
    sides = _EXECUTABLE_SIDES.get(route.route)
    if sides is None:
        raise ValueError(f"V58 execution scope is missing for route {route.route}")
    if route.eligible == 0:
        return "none"
    if route.eligible_by_side is not None:
        executable = sum(route.eligible_by_side[side] for side in sides)
        return "executable" if executable else "observe_only"
    if sides == frozenset({"long", "short"}):
        return "executable"
    return "unresolved"


def _investigation(route: object, experiment: str, why_now: str) -> dict[str, object]:
    return {"route": str(route), "experiment": experiment, "why_now": why_now}
