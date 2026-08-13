"""Growth-first route disposition and after-friction sizing contracts."""

from __future__ import annotations

import pytest

from hypervector.research.growth_first_successor_matrix import (
    GrowthRouteEvidence,
    build_growth_tier_scenarios,
    classify_growth_route,
)


def test_known_negative_route_is_excluded_without_rebranding() -> None:
    """A falsified mechanism cannot return through a new portfolio profile."""
    evidence = _evidence(known_negative=True, exact_forward_closes=20)

    decision = classify_growth_route(evidence)

    assert decision.disposition == "exclude_known_negative"
    assert decision.maximum_tier is None
    assert decision.execution_authority == "none"


def test_technically_unresolved_candidate_remains_capture_only() -> None:
    """Positive development economics cannot override unresolved venue paths."""
    evidence = _evidence(
        technical_resolved=False,
        oos_evaluated=False,
        stress_profit_factor=2.0,
        stress_ex_largest_net_usd=5.0,
    )

    decision = classify_growth_route(evidence)

    assert decision.disposition == "prospective_capture_only"
    assert decision.maximum_tier is None


def test_technical_live_research_starts_at_meaningful_base_tier() -> None:
    """An explicit live research trial uses base risk rather than a token size."""
    evidence = _evidence(
        technical_resolved=True,
        oos_evaluated=False,
        exact_forward_closes=2,
    )

    decision = classify_growth_route(evidence)

    assert decision.disposition == "base_live_research"
    assert decision.maximum_tier == "base"
    assert decision.risk_fraction == pytest.approx(0.01)


def test_strong_and_exceptional_tiers_require_repeatable_outcomes() -> None:
    """Larger tiers require after-cost breadth and largest-winner resilience."""
    strong = classify_growth_route(
        _evidence(
            technical_resolved=True,
            oos_evaluated=True,
            exact_forward_closes=40,
            stress_profit_factor=1.3,
            stress_ex_largest_net_usd=2.0,
            positive_fold_fraction=0.8,
        )
    )
    exceptional = classify_growth_route(
        _evidence(
            technical_resolved=True,
            oos_evaluated=True,
            exact_forward_closes=120,
            stress_profit_factor=1.5,
            stress_ex_largest_net_usd=8.0,
            positive_fold_fraction=0.8,
            sizing_monotonicity_resolved=True,
        )
    )

    assert strong.maximum_tier == "strong"
    assert strong.risk_fraction == pytest.approx(0.015)
    assert exceptional.maximum_tier == "exceptional"
    assert exceptional.risk_fraction == pytest.approx(0.02)


def test_exceptional_tier_requires_explicit_oos_evaluation() -> None:
    """Large close counts cannot imply exceptional evidence without OOS scope."""
    decision = classify_growth_route(
        _evidence(
            technical_resolved=True,
            oos_evaluated=False,
            exact_forward_closes=120,
            stress_profit_factor=1.5,
            stress_ex_largest_net_usd=8.0,
            positive_fold_fraction=0.8,
            sizing_monotonicity_resolved=True,
        )
    )

    assert decision.maximum_tier == "base"


def test_route_evidence_rejects_boolean_counts_and_flags() -> None:
    """Runtime evidence must not accept bool as an integer or status alias."""
    with pytest.raises(ValueError, match="closes must be an integer"):
        _evidence(exact_forward_closes=True)
    with pytest.raises(ValueError, match="technical_resolved must be boolean"):
        _evidence(technical_resolved=1)
    with pytest.raises(ValueError, match="positive fold fraction must be numeric"):
        _evidence(positive_fold_fraction=True)


def test_after_friction_risk_budget_sets_notional_before_leverage() -> None:
    """Leverage manages posted margin; it must not manufacture directional risk."""
    rows = build_growth_tier_scenarios(
        equity_usd=5_000.0,
        stop_bps=80.0,
        fee_bps_per_side=4.5,
        slippage_bps_per_side=2.0,
        venue_max_leverage=10.0,
    )
    by_tier = {row.tier: row for row in rows}

    base = by_tier["base"]
    assert base.notional_usd == pytest.approx(5_000.0 * 0.01 / 0.0093)
    assert base.planned_stop_loss_after_friction_usd == pytest.approx(50.0)
    assert base.leverage == pytest.approx(9.0)
    assert base.margin_fraction < 0.125

    exceptional = by_tier["exceptional"]
    assert exceptional.planned_stop_loss_after_friction_usd == pytest.approx(100.0)
    assert exceptional.leverage == pytest.approx(10.0)
    assert exceptional.leverage_cap_binding is True
    assert exceptional.margin_fraction > base.margin_fraction


def _evidence(**updates: object) -> GrowthRouteEvidence:
    values: dict[str, object] = {
        "route_id": "candidate|BTC|long",
        "technical_resolved": True,
        "oos_evaluated": False,
        "known_negative": False,
        "exact_forward_closes": 0,
        "stress_profit_factor": None,
        "stress_ex_largest_net_usd": None,
        "positive_fold_fraction": None,
        "sizing_monotonicity_resolved": False,
    }
    values.update(updates)
    return GrowthRouteEvidence(**values)
