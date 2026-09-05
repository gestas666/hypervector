"""Contracts for portfolio-wide continuous-improvement telemetry."""

from __future__ import annotations

import pytest

import hypervector.research.cohort_improvement_digest as digest
from v51_change_proposal_fixture import overrides as _proposal_overrides
from v51_change_proposal_fixture import proposal as _proposal


def test_digest_ranks_source_bound_experiments_without_execution_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both-side evidence collection must precede broader mechanism redesign."""
    monkeypatch.setattr(digest, "build_successor_triage", lambda audit: _triage())
    monkeypatch.setattr(digest, "build_side_composition", lambda audit: _sides())

    report = digest.build_cohort_improvement_digest(_audit())

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_retuning": False,
        "automatic_promotion": False,
        "automatic_strategy_changes": False,
        "runtime_strategy_changed": False,
        "performance_gate": False,
        "trade_count_gate": False,
    }
    queue = report["experiment_queue"]
    assert [row["route"] for row in queue] == ["range|SOL", "eth|ETH", "bad|BTC"]
    assert queue[0]["next_experiment"] == "collect_both_side_live_execution"
    assert queue[1]["current_profile_closed_trades"] == 2
    assert report["assessment"]["top_research_priority"] == "range|SOL"
    assert report["side_frontier"]["long"][0]["component"] == "eth|ETH|long"


def test_near_miss_requires_repeatability_after_largest_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nominally positive sparse paths cannot enter the robust near-miss list."""
    monkeypatch.setattr(digest, "build_successor_triage", lambda audit: _triage())
    monkeypatch.setattr(digest, "build_side_composition", lambda audit: _sides())
    audit = _audit()
    audit["execution_opportunity_matrix"]["results"] = [
        _matrix_row("range", "SOL", resolved=4, profit_factor=2.0, ex_largest=8.0),
        _matrix_row("eth", "ETH", resolved=2, profit_factor=3.0, ex_largest=9.0),
        _matrix_row("bad", "BTC", resolved=5, profit_factor=2.0, ex_largest=-1.0),
    ]

    report = digest.build_cohort_improvement_digest(audit)

    assert [row["route"] for row in report["robust_near_misses"]] == ["range|SOL"]
    assert report["robust_near_misses"][0]["automatic_promotion"] is False
    assert report["robust_near_misses"][0]["identity_status"] == (
        "generic_path_requires_exact_mechanic_validation"
    )
    assert report["robust_near_misses"][0]["decision"] == "research_lead_only"


def test_digest_rejects_execution_capable_opportunity_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A research digest must fail closed on execution-capable evidence."""
    monkeypatch.setattr(digest, "build_successor_triage", lambda audit: _triage())
    monkeypatch.setattr(digest, "build_side_composition", lambda audit: _sides())
    audit = _audit()
    audit["execution_opportunity_matrix"]["contract"]["execution_authority"] = (
        "hyperliquid_mainnet"
    )

    with pytest.raises(ValueError, match="opportunity matrix execution authority"):
        digest.build_cohort_improvement_digest(audit)


def test_digest_reports_missing_opportunity_matrix_without_losing_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new live profile must remain observable before paths have matured."""
    monkeypatch.setattr(digest, "build_successor_triage", lambda audit: _triage())
    monkeypatch.setattr(digest, "build_side_composition", lambda audit: _sides())
    audit = _audit()
    audit["execution_opportunity_matrix"] = None

    report = digest.build_cohort_improvement_digest(audit)

    assert len(report["experiment_queue"]) == 3
    assert report["opportunity_matrix_status"] == "unavailable_awaiting_evidence"
    assert report["robust_near_misses"] == []
    assert report["evidence_health"]["opportunity_matrix_available"] is False


def test_rejected_timing_set_updates_research_queue_without_promotion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A newer report-only decision may revise work, never promote execution."""
    monkeypatch.setattr(digest, "build_successor_triage", lambda audit: _triage())
    monkeypatch.setattr(digest, "build_side_composition", lambda audit: _sides())
    overrides = {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
        },
        "routes": {
            "eth|ETH": {
                "triage": "REVISE",
                "next_experiment": "new_side_mechanic_version_required",
                "historical_assessment": "tested_side_timing_set_falsified",
                "decision_source": "decision.json",
                "supporting_evidence": ["current-window.json"],
            }
        },
    }

    report = digest.build_cohort_improvement_digest(
        _audit(), experiment_overrides=overrides
    )

    eth = next(row for row in report["experiment_queue"] if row["route"] == "eth|ETH")
    assert eth["next_experiment"] == "new_side_mechanic_version_required"
    assert eth["historical_assessment"] == "tested_side_timing_set_falsified"
    assert eth["supporting_evidence"] == ["current-window.json"]
    assert eth["execution_effect"] == "report_only"
    assert report["research_decision_overrides"]["applied_routes"] == ["eth|ETH"]


def test_source_parity_override_is_report_only_and_highest_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A source-identity blocker must precede economic route experiments."""
    monkeypatch.setattr(digest, "build_successor_triage", lambda audit: _triage())
    monkeypatch.setattr(digest, "build_side_composition", lambda audit: _sides())
    overrides = {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
        },
        "routes": {
            "eth|ETH": {
                "triage": "REVISE",
                "next_experiment": "collect_and_resolve_source_transport_parity",
                "historical_assessment": "source_contract_unresolved",
                "decision_source": "source-parity.json",
            }
        },
    }

    report = digest.build_cohort_improvement_digest(
        _audit(), experiment_overrides=overrides
    )

    first = report["experiment_queue"][0]
    assert first["route"] == "eth|ETH"
    assert first["next_experiment"] == ("collect_and_resolve_source_transport_parity")
    assert first["execution_effect"] == "report_only"


def test_long_entry_diagnosis_override_is_report_only_and_prioritized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A resolved-loss diagnosis must outrank passive outcome collection."""
    monkeypatch.setattr(digest, "build_successor_triage", lambda audit: _triage())
    monkeypatch.setattr(digest, "build_side_composition", lambda audit: _sides())
    overrides = {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
        },
        "routes": {
            "eth|ETH": {
                "triage": "REVISE",
                "next_experiment": "diagnose_long_entry_quality",
                "historical_assessment": "resolved_loss_needs_entry_attribution",
                "decision_source": "entry-diagnosis.json",
            }
        },
    }

    report = digest.build_cohort_improvement_digest(
        _audit(), experiment_overrides=overrides
    )

    assert report["experiment_queue"][0]["route"] == "eth|ETH"
    assert report["experiment_queue"][0]["execution_effect"] == "report_only"


def test_route_specific_regime_context_override_is_report_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A causal regime challenger must remain research-only and ranked."""
    monkeypatch.setattr(digest, "build_successor_triage", lambda audit: _triage())
    monkeypatch.setattr(digest, "build_side_composition", lambda audit: _sides())
    overrides = {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
        },
        "routes": {
            "range|SOL": {
                "triage": "REVISE",
                "next_experiment": ("collect_route_specific_regime_context_evidence"),
                "historical_assessment": "opposed_paths_adverse_prospectively_unproven",
                "decision_source": "sol-context.json",
            }
        },
    }

    report = digest.build_cohort_improvement_digest(
        _audit(), experiment_overrides=overrides
    )

    sol = next(row for row in report["experiment_queue"] if row["route"] == "range|SOL")
    assert sol["next_experiment"] == ("collect_route_specific_regime_context_evidence")
    assert sol["priority_class"] == 2
    assert sol["execution_effect"] == "report_only"


def test_digest_retains_a_complete_pending_change_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A validated proposal must remain pending and execution-incapable."""
    monkeypatch.setattr(digest, "build_successor_triage", lambda audit: _triage())
    monkeypatch.setattr(digest, "build_side_composition", lambda audit: _sides())

    report = digest.build_cohort_improvement_digest(
        _audit(), experiment_overrides=_proposal_overrides(_proposal())
    )

    proposal = report["research_decision_overrides"]["change_proposals"][0]
    assert proposal["proposal_id"] == "freshness-v1"
    assert proposal["explicit_approval_requested"] is True
    assert proposal["approval_status"] == "pending_human_approval"
    assert proposal["automatic_live_change"] is False
    assert proposal["execution_effect"] == "proposal_only"


def test_digest_rejects_an_incomplete_change_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial recommendation may not become success-shaped approval material."""
    monkeypatch.setattr(digest, "build_successor_triage", lambda audit: _triage())
    monkeypatch.setattr(digest, "build_side_composition", lambda audit: _sides())
    proposal = _proposal()
    proposal.pop("failure_or_rollback_triggers")

    with pytest.raises(ValueError, match="missing required fields"):
        digest.build_cohort_improvement_digest(
            _audit(), experiment_overrides=_proposal_overrides(proposal)
        )


def test_research_override_cannot_promote_a_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decision overlays must fail closed if they request PROCEED."""
    monkeypatch.setattr(digest, "build_successor_triage", lambda audit: _triage())
    monkeypatch.setattr(digest, "build_side_composition", lambda audit: _sides())
    overrides = {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
        },
        "routes": {
            "eth|ETH": {
                "triage": "PROCEED",
                "next_experiment": "shared_portfolio_interaction_replay",
                "historical_assessment": "supportive_candidate",
                "decision_source": "decision.json",
            }
        },
    }

    with pytest.raises(ValueError, match="cannot promote"):
        digest.build_cohort_improvement_digest(_audit(), experiment_overrides=overrides)


def test_digest_carries_report_only_closed_hypothesis_decisions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The continuous layer must receive source-bound closed idea states."""
    monkeypatch.setattr(digest, "build_successor_triage", lambda audit: _triage())
    monkeypatch.setattr(digest, "build_side_composition", lambda audit: _sides())
    decision = {
        "hypothesis_id": "old-gate-relaxation",
        "route": "eth|ETH",
        "experiment": "relax_entry_gate",
        "status": "rejected",
        "decision_reason": "the measured paths were adverse after costs",
        "decision_source": "decision.json",
        "reopen_condition": "new independent causal evidence",
    }
    overrides = {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
        },
        "routes": {},
        "hypothesis_decisions": [decision],
    }

    report = digest.build_cohort_improvement_digest(
        _audit(), experiment_overrides=overrides
    )

    normalized = report["research_decision_overrides"]["hypothesis_decisions"][0]
    assert all(normalized[key] == value for key, value in decision.items())
    assert normalized["execution_effect"] == "report_only"
    assert normalized["automatic_live_change"] is False


def test_digest_exposes_source_bound_first_event_trigger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The moving digest must compare active first-event counters causally."""
    monkeypatch.setattr(digest, "build_successor_triage", lambda audit: _triage())
    monkeypatch.setattr(digest, "build_side_composition", lambda audit: _sides())
    audit = _audit()
    audit["readiness"] = {"by_provider_symbol": {"range|SOL": {"eligible": 1}}}
    audit["routing"] = {
        "strategy_intents": 1,
        "actions": 1,
        "withheld": 0,
        "entry_age_diagnostics": {"eligible_evaluations": 1},
    }
    audit["execution"]["fills"] = 0
    audit["execution"]["closed_trades"] = 0
    audit["execution"]["by_asset"] = {"SOL": {"open_lifecycles": 0}}
    overrides = {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
        },
        "routes": {},
        "active_hypotheses": [_first_event_hypothesis()],
    }

    report = digest.build_cohort_improvement_digest(
        audit, experiment_overrides=overrides
    )

    observation = report["active_hypothesis_observations"][0]
    assert observation["status"] == "eligible_outcome_observed"
    assert observation["counter_deltas"]["eligible_evaluations"] == 1
    assert observation["technical_escalation_required"] is False


def _first_event_hypothesis() -> dict[str, object]:
    return {
        "hypothesis_id": "first-event-v1",
        "status": "being_tested",
        "execution_effect": "report_only",
        "decision_source": "decision.json",
        "evidence_baseline": "baseline.json",
        "baseline_identity": {
            "run_id": "run-1",
            "profile_id": "profile-1",
            "profile_fingerprint": "a" * 64,
        },
        "baseline_counters": {
            field: 0
            for field in (
                "eligible_evaluations",
                "strategy_intents",
                "actions",
                "withheld",
                "fills",
                "open_lifecycles",
                "closed_trades",
            )
        },
    }


def _audit() -> dict[str, object]:
    return {
        "run": {
            "run_id": "run-1",
            "profile_id": "profile-1",
            "profile_fingerprint": "a" * 64,
            "last_observed_at_utc": "2026-08-09T20:00:00+00:00",
        },
        "execution": {
            "closed_trades": 3,
            "wins": 2,
            "losses": 1,
            "net_pnl_usd": 1.25,
            "profit_factor": 2.0,
            "fees_usd": 0.2,
            "funding_usd": -0.01,
        },
        "portfolio": {
            "final_equity_usd": 501.25,
            "maximum_drawdown_pct": 0.4,
        },
        "coverage": {"complete": False, "technical_gaps": ["old_metric_gap"]},
        "signal_outcomes": {
            "coverage": {
                "metric_value_gaps": 3,
                "right_censored_observations": 4,
            }
        },
        "health": {"faults": 0, "assets": {}},
        "execution_opportunity_matrix": {
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "live_strategy_changed": False,
            },
            "results": [],
            "supplemental_forward_challengers": [],
        },
    }


def _triage() -> dict[str, object]:
    return {
        "summary": {"routes": 3, "proceed": 0, "revise": 2, "stop_exact_contract": 1},
        "routes": {
            "bad|BTC": _route("STOP", "new_side_mechanic_version_required", 4, 12),
            "eth|ETH": _route("REVISE", "separate_long_short_mechanisms", 2, 8),
            "range|SOL": _route("REVISE", "collect_both_side_live_execution", 0, 4),
        },
    }


def _route(triage: str, experiment: str, trades: int, paths: int) -> dict[str, object]:
    return {
        "triage": triage,
        "next_experiment": experiment,
        "historical_assessment": "supportive_candidate",
        "cost_survival": "unavailable"
        if trades == 0
        else "positive_after_observed_costs",
        "concentration": "unavailable",
        "live_translation": {
            "closed_trades": trades,
            "wins": trades,
            "losses": 0,
            "net_pnl_usd": float(trades),
            "profit_factor": None,
            "observed_sides": ["long"] if trades else [],
        },
        "forward_path_evidence": {"independent_paths": paths, "resolved_horizons": 4},
    }


def _sides() -> dict[str, object]:
    return {
        "summary": {
            "components": 2,
            "long_frontier_components": 1,
            "short_frontier_components": 1,
        },
        "frontier": {
            "long": [{"component": "eth|ETH|long", "trades": 2}],
            "short": [{"component": "range|SOL|short", "trades": 0}],
        },
    }


def _matrix_row(
    strategy: str,
    symbol: str,
    *,
    resolved: int,
    profit_factor: float,
    ex_largest: float,
) -> dict[str, object]:
    return {
        "strategy_id": strategy,
        "symbol": symbol,
        "blocker": "one_blocker",
        "opi_cohort": "aligned",
        "resolved": resolved,
        "wins": resolved - 1,
        "losses": 1,
        "total_net_return_bps": 10.0,
        "profit_factor": profit_factor,
        "net_return_excluding_largest_winner_bps": ex_largest,
        "largest_abs_contribution_fraction": 0.4,
        "long": {"resolved": resolved},
        "short": {"resolved": 0},
    }
