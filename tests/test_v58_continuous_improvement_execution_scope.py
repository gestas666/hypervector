"""Execution-scope regressions for V58 opportunity prioritization."""

from __future__ import annotations

from datetime import UTC, datetime

from hypervector.research.cohort_successor_observer_status import (
    SuccessorObserverEvidence,
)
from hypervector.research.v58_continuous_improvement import (
    LifecycleEvidence,
    RouteOpportunity,
    RouteOpportunityCollection,
    build_v58_continuous_improvement,
)
from hypervector.research.v58_route_opportunity import parse_route_opportunity
from hypervector.research.v58_continuous_generator_paths import (
    v58_continuous_generator_paths,
)
from v58_continuous_improvement_fixtures import v58_route, v58_route_keys


def test_observe_only_sndk_long_does_not_request_live_lifecycle_capture() -> None:
    """A long signal cannot create a lifecycle on V58's short-only SNDK route."""
    report = build_v58_continuous_improvement(
        _observer(),
        _lifecycle("BTC", v58_route("BTC_SWEEP")),
        _lifecycle("ETH", v58_route("ETH"), pending=1),
        _lifecycle("HYPE", v58_route("HYPE")),
        _lifecycle("xyz:SP500", v58_route("xyz:SP500")),
        _opportunities_with_sndk_long(),
        generated_at=datetime(2026, 8, 20, 7, 0, tzinfo=UTC),
    )

    assert report["highest_value_next_investigation"] == {
        "route": v58_route("ETH"),
        "experiment": "resolve_open_exact_lifecycle",
        "why_now": "one source-compatible lifecycle is open under frozen exits",
    }
    coverage = report["lifecycle_capture_coverage"]
    sndk = next(
        row for row in coverage["routes"] if row["route"] == v58_route("xyz:SNDK")
    )
    assert coverage["eligible_without_exact_capture"] == 0
    assert sndk["status"] == "observe_only_eligible_without_live_authority"


def test_later_ineligible_short_does_not_relabel_prior_long_eligibility() -> None:
    """Eligibility side counts must outrank the latest ineligible readiness side."""
    opportunities = _opportunities_with_sndk_long()
    rows = tuple(
        _sndk_historical_long_latest_short()
        if item.route == v58_route("xyz:SNDK")
        else item
        for item in opportunities.opportunities
    )
    report = build_v58_continuous_improvement(
        _observer(),
        _lifecycle("BTC", v58_route("BTC_SWEEP")),
        _lifecycle("ETH", v58_route("ETH"), pending=1),
        _lifecycle("HYPE", v58_route("HYPE")),
        _lifecycle("xyz:SP500", v58_route("xyz:SP500")),
        RouteOpportunityCollection(rows, opportunities.evidence),
        generated_at=datetime(2026, 8, 20, 7, 5, tzinfo=UTC),
    )

    assert report["highest_value_next_investigation"]["route"] == v58_route("ETH")
    sndk = next(
        row
        for row in report["lifecycle_capture_coverage"]["routes"]
        if row["route"] == v58_route("xyz:SNDK")
    )
    assert sndk["status"] == "observe_only_eligible_without_live_authority"


def test_missing_side_counts_do_not_infer_authority_from_latest_side() -> None:
    """Legacy aggregate readiness must not guess an eligible event's side."""
    opportunities = _opportunities_with_sndk_long(include_side_counts=False)
    report = build_v58_continuous_improvement(
        _observer(),
        _lifecycle("BTC", v58_route("BTC_SWEEP")),
        _lifecycle("ETH", v58_route("ETH"), pending=1),
        _lifecycle("HYPE", v58_route("HYPE")),
        _lifecycle("xyz:SP500", v58_route("xyz:SP500")),
        opportunities,
        generated_at=datetime(2026, 8, 20, 7, 10, tzinfo=UTC),
    )

    assert report["highest_value_next_investigation"]["route"] == v58_route("ETH")
    sndk = next(
        row
        for row in report["lifecycle_capture_coverage"]["routes"]
        if row["route"] == v58_route("xyz:SNDK")
    )
    assert sndk["status"] == "eligible_execution_side_attribution_unavailable"


def test_capture_priority_module_is_frozen_in_generator_identity() -> None:
    """The long-running report must abort if capture-priority logic changes."""
    paths = {str(path) for path in v58_continuous_generator_paths("script.py")}

    assert "src/hypervector/research/v58_lifecycle_capture.py" in paths


def _observer() -> SuccessorObserverEvidence:
    return SuccessorObserverEvidence(
        status={
            "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
            "profile_fingerprint": "profile",
            "run_id": "run",
            "freshness_status": "fresh",
            "technical_complete": True,
            "provider_symbol_routes": 10,
            "routed_actions": 0,
            "report_only": True,
            "execution_authority": "none",
        },
        evidence={"sha256": "observer"},
    )


def _lifecycle(symbol: str, route: str, *, pending: int = 0) -> LifecycleEvidence:
    return LifecycleEvidence(
        symbol=symbol,
        route=route,
        state="awaiting_resolution",
        pending=pending,
        resolved=0,
        technical_complete=True,
        source_age_seconds=1.0,
        evidence={"sha256": symbol},
    )


def _opportunities_with_sndk_long(
    *, include_side_counts: bool = True
) -> RouteOpportunityCollection:
    opportunities = tuple(
        _opportunity(
            v58_route(key),
            eligible=1 if key == "xyz:SNDK" else 0,
            latest_side="long" if key == "xyz:SNDK" else None,
            include_side_counts=include_side_counts,
        )
        for key in v58_route_keys()
    )
    return RouteOpportunityCollection(opportunities, {"sha256": "routes"})


def _opportunity(
    route: str,
    *,
    eligible: int,
    latest_side: str | None,
    include_side_counts: bool,
) -> RouteOpportunity:
    return RouteOpportunity(
        route=route,
        evaluations=10,
        eligible=eligible,
        first_fraction=0.5,
        minimum_fraction=0.5,
        mean_fraction=0.5,
        latest_fraction=1.0 if eligible else 0.5,
        maximum_fraction=1.0 if eligible else 0.75,
        progressions=0,
        regressions=0,
        state_transitions=0,
        unchanged=9,
        blocker_counts={"waiting": 9 if eligible else 10},
        reason_counts={"ready": eligible, "waiting": 10 - eligible},
        latest_reason="ready" if eligible else "waiting",
        latest_side=latest_side,
        research_state="unresolved",
        confidence="low",
        eligible_by_side=(
            {"long": eligible, "short": 0} if include_side_counts else None
        ),
    )


def _sndk_historical_long_latest_short() -> RouteOpportunity:
    return parse_route_opportunity(
        v58_route("xyz:SNDK"),
        {
            "count": 2,
            "eligible": 1,
            "eligible_by_side": {"long": 1, "short": 0},
            "first_fraction": 1.0,
            "minimum_fraction": 0.5,
            "mean_fraction": 0.75,
            "latest_fraction": 0.5,
            "maximum_fraction": 1.0,
            "progressions": 0,
            "regressions": 1,
            "state_transitions": 1,
            "unchanged": 0,
            "blockers": {"breakout_level_not_crossed": 1},
            "reasons": {"breakout_pressure_confirmed": 1, "waiting": 1},
            "latest_reason": "waiting",
            "latest_side": "short",
        },
        {"research_state": "unresolved", "confidence": "low"},
    )
