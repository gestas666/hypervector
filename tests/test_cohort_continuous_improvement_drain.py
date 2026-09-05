"""Transition-drain availability contracts for continuous research."""

from __future__ import annotations

from hypervector.research.cohort_continuous_improvement import (
    build_continuous_improvement_report,
)
from test_cohort_continuous_improvement import _checkpoint, _digest


def test_active_drain_suspends_live_collection_and_keeps_report_only_work() -> None:
    """A drain must not rank evidence collection that requires new entries."""
    checkpoint = _checkpoint()
    checkpoint["transition_drain"] = {"status": "active"}

    report = build_continuous_improvement_report(checkpoint, _digest())

    queue = {row["route"]: row for row in report["experiment_queue"]}
    assert queue["range|SOL"]["research_availability"] == (
        "suspended_by_transition_drain"
    )
    assert queue["index|xyz:SP500"]["research_availability"] == (
        "suspended_by_transition_drain"
    )
    assert queue["hype|HYPE"]["research_availability"] == "available_report_only"
    assert report["highest_value_next_investigation"] == {
        "route": "hype|HYPE",
        "experiment": "diagnose_signal_cost_or_concentration",
        "why_now": "highest-ranked investigation executable during active drain",
        "automatic_live_change": False,
    }
    ranked = {row["route"] for row in report["opportunity_ranking"]}
    assert "range|SOL" not in ranked
    assert "index|xyz:SP500" not in ranked
    assert report["assessment"]["top_research_priority"] == "hype|HYPE"
    assert report["assessment"]["suspended_experiments"] == 4


def test_inactive_run_preserves_all_research_availability() -> None:
    """Normal live collection remains eligible before a drain is activated."""
    report = build_continuous_improvement_report(_checkpoint(), _digest())

    assert all(
        row["research_availability"] == "available_report_only"
        for row in report["experiment_queue"]
    )
