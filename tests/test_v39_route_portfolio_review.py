"""Tests for the exact-v39 route and portfolio evidence review."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hypervector.research.v39_forward_evidence import build_v39_forward_evidence
from hypervector.research.v39_route_portfolio_review import (
    build_v39_route_portfolio_review,
)
from v39_forward_evidence_fixtures import (
    checkpoint,
    config,
    install_current_run,
    routes,
)


def test_review_keeps_current_history_and_research_evidence_separate() -> None:
    """One current close cannot be relabeled as mixed-history route evidence."""
    live_config = config()
    source = checkpoint(live_config)
    route = routes(live_config)[0]
    install_current_run(source, route)
    _install_review_sections(source, route)
    forward = build_v39_forward_evidence(
        source,
        live_config,
        observed_at=datetime(2026, 8, 11, 10, 0, 30, tzinfo=UTC),
    )

    report = build_v39_route_portfolio_review(forward, source)
    reviewed = report["routes"][route]

    assert report["summary"]["provider_symbol_routes"] == 14
    assert report["summary"]["current_run_closed_trades"] == 1
    assert report["summary"]["all_time_descriptive_closed_trades"] == 3
    assert reviewed["current_run"]["closed"]["closed_trades"] == 1
    assert reviewed["all_time_descriptive"]["closed_trades"] == 3
    assert reviewed["research_context"]["research_state"] == "contradictory"
    assert reviewed["evidence_state"] == "resolved_current_run_close"
    assert report["portfolio_assessment"]["growth_scaling_state"] == (
        "sizing_only_route_edge_not_established"
    )
    challengers = report["causal_challenger_program"]
    assert challengers["current_exact_sample"]["resolved_closed_lifecycles"] == 1
    assert challengers["contract"]["execution_authority"] == "none"
    assert challengers["assessment"]["model_fit_now"] is False
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["performance_gate"] is False


def test_review_reports_exact_current_run_friction_and_signal_frequency() -> None:
    """Actual v39 fills and eligibility cadence remain route attributable."""
    live_config = config()
    source = checkpoint(live_config)
    route = routes(live_config)[0]
    install_current_run(source, route)
    trade = source["audit"]["trade_reflections"]["trades"][0]
    trade["entry"]["slippage_bps"] = 1.25
    trade["exit"]["slippage_bps"] = 2.75
    _install_review_sections(source, route)
    source["audit"]["signal_outcomes"]["by_provider_symbol"][route] = {
        "evaluations": 4,
        "eligible_evaluations": 1,
        "no_direction": 2,
        "by_side": {
            "long": {"evaluations": 1, "eligible_evaluations": 1},
            "short": {"evaluations": 1, "eligible_evaluations": 0},
        },
    }
    forward = build_v39_forward_evidence(
        source,
        live_config,
        observed_at=datetime(2026, 8, 11, 10, 0, 30, tzinfo=UTC),
    )

    reviewed = build_v39_route_portfolio_review(forward, source)["routes"][route]

    assert reviewed["current_run"]["eligible_rate_pct"] == pytest.approx(25.0)
    assert reviewed["current_run"]["friction"]["entry_slippage_bps"] == {
        "observations": 1,
        "mean": 1.25,
        "maximum": 1.25,
        "status": "observed",
    }
    assert reviewed["current_run"]["friction"]["exit_slippage_bps"]["mean"] == 2.75


def test_review_rejects_research_or_runtime_identity_gaps() -> None:
    """Every route requires exact current and research identity coverage."""
    live_config = config()
    source = checkpoint(live_config)
    route = routes(live_config)[0]
    _install_review_sections(source, route)
    source["audit"]["strategy_scorecard"]["by_provider_symbol"].pop(route)
    forward = build_v39_forward_evidence(
        source,
        live_config,
        observed_at=datetime(2026, 8, 11, 10, 0, 30, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="research route coverage"):
        build_v39_route_portfolio_review(forward, source)


def _install_review_sections(source: dict[str, object], route: str) -> None:
    audit = source["audit"]
    route_ids = list(audit["routing"]["executable_provider_symbols"])
    audit["portfolio_archive"] = {
        "coverage": {"complete": True, "closed_orders": 3},
        "performance": {
            "total": {"closed_trades": 3},
            "by_provider_symbol": {
                route: {
                    "closed_trades": 3,
                    "wins": 2,
                    "losses": 1,
                    "breakeven": 0,
                    "net_pnl_usd": 0.5,
                    "profit_factor": 1.2,
                    "net_pnl_excluding_largest_winner_usd": -0.1,
                    "fees_usd": 0.2,
                    "funding_usd": 0.01,
                }
            },
        },
    }
    audit["strategy_scorecard"] = {
        "by_provider_symbol": {
            item: {
                "research_state": "contradictory",
                "forward_assessment": "no_eligible_signal_evidence",
                "historical_summary": "fixture historical evidence",
                "confidence": "medium",
                "eligible_signal_horizons": {},
            }
            for item in route_ids
        }
    }
    audit["canonical_regime_telemetry"] = {
        "contract": {"execution_authority": "none", "intents_emitted": False},
        "by_symbol": {},
    }
