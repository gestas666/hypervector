"""Contracts for the v51 continuous-improvement research layer."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_continuous_improvement import (
    build_continuous_improvement_report,
)


def test_report_corrects_research_work_for_exact_configured_sides() -> None:
    """Research work must respect the live route's frozen directional scope."""
    report = build_continuous_improvement_report(_checkpoint(), _digest())

    rows = {row["route"]: row for row in report["experiment_queue"]}
    assert rows["sweep|BTC"]["configured_directions"] == ["long"]
    assert rows["sweep|BTC"]["next_experiment"] == ("collect_side_specific_evidence")
    assert rows["hulk|BTC"]["configured_directions"] == ["short"]
    assert rows["hulk|BTC"]["next_experiment"] == ("collect_side_specific_evidence")
    assert rows["index|xyz:SP500"]["next_experiment"] == (
        "collect_both_side_live_execution"
    )
    assert rows["hype|HYPE"]["next_experiment"] == (
        "diagnose_signal_cost_or_concentration"
    )
    assert rows["range|SOL"]["next_experiment"] == ("collect_both_side_live_execution")


def test_report_exposes_traceable_hypotheses_and_approval_boundary() -> None:
    """Every active route needs a measurable, non-executable research record."""
    report = build_continuous_improvement_report(_checkpoint(), _digest())

    assert report["highest_value_next_investigation"]["route"] == "range|SOL"
    assert {row["status"] for row in report["hypothesis_ledger"]} == {"being_tested"}
    assert all(
        row["minimum_additional_evidence"] for row in report["hypothesis_ledger"]
    )
    assert report["change_proposals"] == []
    assert report["human_approval_boundary"]["required_before_live_change"] is True
    assert report["proposal_contract"]["required_fields"] == [
        "recommendation",
        "why_now",
        "evidence_reviewed",
        "observed_problem_or_opportunity",
        "applicable_market_regime",
        "alternatives_considered",
        "proposed_live_change",
        "expected_upside",
        "main_risks_and_failure_modes",
        "validation_completed",
        "validation_still_required",
        "success_metrics",
        "failure_or_rollback_triggers",
        "confidence_level",
        "explicit_approval_requested",
    ]


def test_report_rejects_route_scope_missing_from_live_checkpoint() -> None:
    """A digest cannot silently analyze a route absent from live configuration."""
    checkpoint = _checkpoint()
    directions = checkpoint["configuration_generation"]
    directions["current_provider_execution_directions"].pop("sweep|BTC")

    with pytest.raises(ValueError, match="route scope does not match digest"):
        build_continuous_improvement_report(checkpoint, _digest())


def test_report_escalates_an_open_position_without_venue_protection() -> None:
    """Protection loss is a material defect even before a fault is emitted."""
    checkpoint = _checkpoint()
    checkpoint["lifecycle"]["asset_states"]["BTC"] = "OPEN"
    checkpoint["audit"]["health"]["assets"] = {
        "BTC": {"position_size_signed": 0.1, "protected_if_open": False}
    }

    report = build_continuous_improvement_report(checkpoint, _digest())

    assessment = report["operational_assessment"]
    assert assessment["status"] == "material_defect"
    assert assessment["escalation_required"] is True
    assert assessment["unprotected_assets"] == ["BTC"]


def _checkpoint() -> dict[str, object]:
    routes = {
        "range|SOL": ["long", "short"],
        "index|xyz:SP500": ["long", "short"],
        "hype|HYPE": ["long", "short"],
        "sweep|BTC": ["long"],
        "hulk|BTC": ["short"],
    }
    scorecard = {
        "range|SOL": _score("historical_candidate", {"long": {}, "short": {}}),
        "index|xyz:SP500": _score(
            "prospective_v3_technical_parity_live_outcomes_unresolved", {}
        ),
        "hype|HYPE": _score(
            "development_positive_fold_unstable_confirmation_concentrated", {}
        ),
        "sweep|BTC": _score("taker_parity_promising_path_unresolved", {}),
        "hulk|BTC": _score("forward_exact_n1_repeatability_unproven", {}),
    }
    return {
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "lifecycle": {
            "state": "running_consistent",
            "backend_process_health": "healthy",
            "cohort_heartbeat_age_seconds": 5.0,
            "faulted_assets": [],
            "asset_states": {"BTC": "FLAT", "SOL": "FLAT"},
        },
        "configuration_generation": {
            "matches_runtime": True,
            "state": "current_runtime_configuration",
            "current_provider_execution_directions": routes,
        },
        "audit": {
            "run": {
                "run_id": "run-51",
                "profile_id": "profile-51",
                "profile_fingerprint": "a" * 64,
                "executable_provider_symbols": list(routes),
            },
            "health": {"faults": 0},
            "strategy_scorecard": {"by_provider_symbol": scorecard},
        },
    }


def _score(state: str, directional: dict[str, object]) -> dict[str, object]:
    return {
        "research_state": state,
        "confidence": "medium",
        "directional_research": directional,
        "execution_outcomes_identifiable": False,
        "eligible_signals": 0,
        "evidence_source": "evidence.json",
    }


def _digest() -> dict[str, object]:
    return {
        "contract": {"report_only": True, "execution_authority": "none"},
        "source": {
            "run_id": "run-51",
            "profile_id": "profile-51",
            "profile_fingerprint": "a" * 64,
        },
        "performance": {"closed_trades": 0, "net_pnl_usd": 0.0},
        "experiment_queue": [
            _queue("range|SOL", "collect_both_side_live_execution", 1),
            _queue("index|xyz:SP500", "separate_long_short_mechanisms", 2),
            _queue("hype|HYPE", "separate_long_short_mechanisms", 3),
            _queue("sweep|BTC", "separate_long_short_mechanisms", 4),
            _queue("hulk|BTC", "establish_source_backed_mechanism", 5),
        ],
    }


def _queue(route: str, experiment: str, rank: int) -> dict[str, object]:
    return {
        "route": route,
        "triage": "REVISE",
        "next_experiment": experiment,
        "historical_assessment": "supportive_candidate",
        "current_profile_closed_trades": 0,
        "research_rank": rank,
        "priority_class": rank,
        "execution_effect": "report_only",
    }
