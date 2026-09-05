"""Contracts for the v51 continuous-improvement research layer."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_continuous_improvement import (
    build_continuous_improvement_report,
)
from v51_change_proposal_fixture import proposal as _proposal


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


def test_report_exposes_transparent_opportunity_ranking() -> None:
    """Research priority must expose all mandated decision dimensions."""
    report = build_continuous_improvement_report(_checkpoint(), _digest())

    ranking = report["opportunity_ranking"]
    assert ranking[0]["route"] == report["highest_value_next_investigation"]["route"]
    assert ranking[0]["expected_economic_value"] == (
        "unquantified_until_compatible_forward_lifecycles"
    )
    assert ranking[0]["expected_information_value"] == "high"
    assert ranking[0]["confidence"] == "medium"
    assert ranking[0]["implementation_complexity"] == "none_for_observation"
    assert ranking[0]["downside"] == "sparse_evidence_can_mislead"
    assert ranking[0]["validation_priority"] == 1


def test_report_exposes_traceable_hypotheses_and_approval_boundary() -> None:
    """Every active route needs a measurable, non-executable research record."""
    report = build_continuous_improvement_report(_checkpoint(), _digest())

    assert report["highest_value_next_investigation"]["route"] == "range|SOL"
    assert {row["status"] for row in report["hypothesis_ledger"]} == {"being_tested"}
    assert all(
        row["minimum_additional_evidence"] for row in report["hypothesis_ledger"]
    )
    assert report["change_proposals"] == []
    assert report["mandate_evidence"]["execution"] == {
        "status": "unavailable",
        "reason": "execution_or_routing_unavailable",
    }
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


def test_report_preserves_a_source_bound_research_decision_override() -> None:
    """A frozen research decision must outrank generic scorecard normalization."""
    digest = _digest()
    hype = next(
        row for row in digest["experiment_queue"] if row["route"] == "hype|HYPE"
    )
    hype.update(
        {
            "next_experiment": "new_mechanic_version_required",
            "decision_source": "hype-decision.json",
            "supporting_evidence": ["hype-window.json"],
        }
    )

    report = build_continuous_improvement_report(_checkpoint(), digest)

    actual = next(
        row for row in report["experiment_queue"] if row["route"] == "hype|HYPE"
    )
    assert actual["next_experiment"] == "new_mechanic_version_required"
    assert actual["side_scope_adjusted"] is False
    hypothesis = next(
        row for row in report["hypothesis_ledger"] if row["route"] == "hype|HYPE"
    )
    assert hypothesis["evidence_reviewed"] == [
        "hype-decision.json",
        "hype-window.json",
        "evidence.json",
    ]


def test_source_parity_override_remains_the_highest_value_investigation() -> None:
    """A frozen technical-validity experiment must not be demoted by scorecards."""
    digest = _digest()
    index = next(
        row for row in digest["experiment_queue"] if row["route"] == "index|xyz:SP500"
    )
    index.update(
        {
            "next_experiment": "collect_and_resolve_source_transport_parity",
            "decision_source": "source-parity.json",
        }
    )

    report = build_continuous_improvement_report(_checkpoint(), digest)

    assert report["highest_value_next_investigation"] == {
        "route": "index|xyz:SP500",
        "experiment": "collect_and_resolve_source_transport_parity",
        "why_now": "highest-ranked unresolved v51 evidence question",
        "automatic_live_change": False,
    }


def test_report_labels_research_with_the_current_profile_generation() -> None:
    """A successor digest must not retain stale v51 research identity labels."""
    checkpoint = _checkpoint()
    digest = _digest()
    profile = "multi_asset_growth_first_5000_evidence_bound_successor_v52"
    checkpoint["audit"]["run"]["profile_id"] = profile
    digest["source"]["profile_id"] = profile

    report = build_continuous_improvement_report(checkpoint, digest)

    assert report["highest_value_next_investigation"]["why_now"] == (
        "highest-ranked unresolved v52 evidence question"
    )
    assert report["baseline_comparison"] == {
        "baseline": "v52_current_live_contract",
        "no_action": "continue_current_v52_and_collect_attributable_evidence",
        "compatible_closed_trades": 0,
        "measured_change_delta": None,
        "reason": "no approved change candidate exists",
    }
    active = [
        row for row in report["hypothesis_ledger"] if row["status"] == "being_tested"
    ]
    assert active
    assert all(
        row["hypothesis_id"].startswith("v52-live-translation:") for row in active
    )
    assert all("exact v52 route" in row["hypothesis"] for row in active)


def test_report_preserves_route_specific_regime_context_hypothesis() -> None:
    """A source-bound regime cohort must remain explicit and report-only."""
    digest = _digest()
    sol = next(row for row in digest["experiment_queue"] if row["route"] == "range|SOL")
    sol.update(
        {
            "next_experiment": "collect_route_specific_regime_context_evidence",
            "decision_source": "sol-context.json",
        }
    )

    report = build_continuous_improvement_report(_checkpoint(), digest)

    actual = next(
        row for row in report["experiment_queue"] if row["route"] == "range|SOL"
    )
    assert actual["priority_class"] == 2
    hypothesis = next(
        row for row in report["hypothesis_ledger"] if row["route"] == "range|SOL"
    )
    assert hypothesis["experiment"] == (
        "collect_route_specific_regime_context_evidence"
    )
    assert hypothesis["hypothesis"] == (
        "route-specific clear multi-timeframe context improves the exact v51 "
        "route after costs"
    )
    assert hypothesis["execution_effect"] == "report_only"


def test_report_retains_closed_hypothesis_decisions() -> None:
    """Resolved ideas must remain closed beside the current route experiment."""
    digest = _digest()
    digest["research_decision_overrides"] = {
        "hypothesis_decisions": [
            {
                "hypothesis_id": "hype-old-profit-lock",
                "route": "hype|HYPE",
                "experiment": "generic_profit_lock_family",
                "status": "rejected",
                "decision_reason": "all tested locks underperformed the control",
                "decision_source": "hype-decision.json",
                "reopen_condition": "a new causal exit family with untouched evidence",
            }
        ]
    }

    report = build_continuous_improvement_report(_checkpoint(), digest)

    rejected = next(
        row
        for row in report["hypothesis_ledger"]
        if row["hypothesis_id"] == "hype-old-profit-lock"
    )
    assert rejected["status"] == "rejected"
    active = next(
        row
        for row in report["hypothesis_ledger"]
        if row["route"] == "hype|HYPE" and row["status"] == "being_tested"
    )
    assert active["hypothesis_id"].endswith(f":{active['experiment']}")


def test_report_exposes_only_a_pending_human_approved_change_proposal() -> None:
    """A proposal may request approval but cannot grant itself live authority."""
    digest = _digest()
    digest["research_decision_overrides"] = {
        "change_proposals": [_proposal()],
    }

    report = build_continuous_improvement_report(_checkpoint(), digest)

    assert report["change_proposals"] == [_proposal()]
    assert report["proposal_contract"]["execution_authority"] == "none"
    assert report["proposal_contract"]["automatic_live_change"] is False


def test_report_retains_approved_change_without_deployment_authority() -> None:
    """Recorded approval must not become automatic deployment authority."""
    digest = _digest()
    approved = _proposal()
    approved.update(
        {
            "approval_status": "approved_waiting_flat_boundary",
            "approval_evidence": "approval-ledger.json",
            "execution_effect": "approved_not_deployed",
            "explicit_approval_requested": False,
        }
    )
    digest["research_decision_overrides"] = {"change_proposals": [approved]}

    report = build_continuous_improvement_report(_checkpoint(), digest)

    actual = report["change_proposals"][0]
    assert actual["approval_status"] == "approved_waiting_flat_boundary"
    assert actual["approval_evidence"] == "approval-ledger.json"
    assert actual["execution_effect"] == "approved_not_deployed"
    assert actual["automatic_live_change"] is False
    assert actual["explicit_approval_requested"] is False


def test_report_surfaces_live_paths_even_without_opportunity_matrix() -> None:
    """Current-run readiness paths must reach the continuous report."""
    checkpoint = _checkpoint()
    _attach_live_diagnostics(checkpoint)

    report = build_continuous_improvement_report(checkpoint, _digest())

    diagnostics = report["live_opportunity_diagnostics"]
    assert diagnostics["status"] == "available"
    assert len(diagnostics["routes"]) == 5
    assert diagnostics["routes"][0]["scarcity_interpretation"] == (
        "zero_eligible_signal_observed_no_frequency_conclusion"
    )
    assert diagnostics["contract"]["automatic_live_change"] is False


def test_report_surfaces_report_only_entry_age_diagnostics() -> None:
    """The research layer must retain cutoff versus routing-age evidence."""
    checkpoint = _checkpoint()
    checkpoint["audit"]["routing"] = {
        "entry_age_diagnostics": {
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "entry_enforcement_changed": False,
            },
            "paired_cycles": 12,
            "evaluations": 29,
            "eligible_evaluations": 0,
            "enter_actions": 0,
            "enter_actions_routing_emission_over_limit": 0,
            "executed_late_entries_proven": False,
            "submission_timestamp_observed": False,
            "by_provider_symbol": {},
            "limitations": ["submit time is not observed"],
        }
    }

    report = build_continuous_improvement_report(checkpoint, _digest())

    diagnostics = report["execution_diagnostics"]["entry_age"]
    assert diagnostics["paired_cycles"] == 12
    assert diagnostics["executed_late_entries_proven"] is False
    assert diagnostics["contract"]["execution_authority"] == "none"


def test_report_accepts_observed_entry_submission_enforcement() -> None:
    """Exact submission evidence must remain visible to the improvement loop."""
    checkpoint = _checkpoint()
    checkpoint["audit"]["routing"] = {
        "entry_age_diagnostics": _submission_diagnostic(executed_late=False)
    }

    report = build_continuous_improvement_report(checkpoint, _digest())

    execution = report["execution_diagnostics"]
    assert execution["status"] == "available"
    assert execution["entry_age"]["submission_timestamp_observed"] is True
    assert execution["entry_age"]["entry_submission_enforcement_observed"] is True


def test_report_escalates_proven_late_entry_without_discarding_evidence() -> None:
    """A proven late submission is a defect, not an invalid report shape."""
    checkpoint = _checkpoint()
    checkpoint["audit"]["routing"] = {
        "entry_age_diagnostics": _submission_diagnostic(executed_late=True)
    }

    report = build_continuous_improvement_report(checkpoint, _digest())

    assert report["execution_diagnostics"]["status"] == ("material_execution_defect")


def _submission_diagnostic(*, executed_late: bool) -> dict[str, object]:
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "entry_enforcement_changed": True,
        },
        "executed_late_entries_proven": executed_late,
        "submission_timestamp_observed": True,
        "entry_submission_enforcement_observed": True,
        "submitted_entries": 1,
        "stale_entries_withheld": 0,
        "by_provider_symbol": {},
        "limitations": [],
    }


def test_report_rejects_entry_age_evidence_with_execution_authority() -> None:
    """A diagnostic carrying execution authority cannot enter the report."""
    checkpoint = _checkpoint()
    checkpoint["audit"]["routing"] = {
        "entry_age_diagnostics": {
            "contract": {
                "report_only": True,
                "execution_authority": "hyperliquid_mainnet",
                "entry_enforcement_changed": False,
            }
        }
    }

    with pytest.raises(ValueError, match="entry-age diagnostic is not report-only"):
        build_continuous_improvement_report(checkpoint, _digest())


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


def _attach_live_diagnostics(checkpoint: dict[str, object]) -> None:
    audit = checkpoint["audit"]
    routes = checkpoint["configuration_generation"]
    route_names = routes["current_provider_execution_directions"]
    audit["run"].update(
        {
            "first_observed_at_utc": "2026-08-13T21:00:00+00:00",
            "last_observed_at_utc": "2026-08-13T22:00:00+00:00",
        }
    )
    audit["readiness"] = {
        "by_provider_symbol": {route: _readiness() for route in route_names}
    }
    audit["signal_outcomes"] = {
        "evaluations": len(route_names),
        "eligible_evaluations": 0,
        "directional_evaluations": len(route_names),
        "coverage": {"right_censored_observations": 0},
        "by_provider_symbol": {route: _outcomes() for route in route_names},
    }


def _readiness() -> dict[str, object]:
    return {
        "count": 1,
        "eligible": 0,
        "latest_fraction": 0.5,
        "latest_blockers": ["gate_absent"],
        "blockers": {"gate_absent": 1},
    }


def _outcomes() -> dict[str, object]:
    return {
        "evaluations": 1,
        "by_evidence_class": {"eligible_signal": {"evaluations": 0}},
        "one_blocker_near_misses": {"by_blocker": {}},
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
