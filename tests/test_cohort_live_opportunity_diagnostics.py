"""Contracts for exact current-run signal-scarcity diagnostics."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_live_opportunity_diagnostics import (
    build_live_opportunity_diagnostics,
)


def test_diagnostics_surface_mature_one_blocker_paths_without_promoting() -> None:
    """Mature readiness paths must not disappear when the matrix is absent."""
    report = build_live_opportunity_diagnostics(_audit())

    assert report["status"] == "available"
    assert report["totals"] == {
        "evaluations": 12,
        "eligible_evaluations": 0,
        "directional_evaluations": 12,
        "right_censored_observations": 7,
    }
    route = report["routes"][0]
    assert route["route"] == "strategy|SOL"
    assert route["signal_outcomes_status"] == "available"
    assert route["scarcity_interpretation"] == (
        "zero_eligible_signal_observed_no_frequency_conclusion"
    )
    assert route["latest_blockers"] == ["gate_absent"]
    assert route["historical_cadence_currentness"] == "frozen_prior_evidence"
    assert route["current_live_execution"]["status"] == "no_resolved_lifecycles"
    assert route["current_live_execution"]["closed_lifecycles"] == 0
    assert route["decision_side_coverage"] == {
        "status": "available",
        "by_side": {
            "long": {"evaluations": 8, "eligible_evaluations": 0},
            "short": {"evaluations": 4, "eligible_evaluations": 0},
        },
        "directional_evaluations": 12,
        "nondirectional_evaluations": 0,
        "observed_sides": ["long", "short"],
        "eligible_sides": [],
        "both_sides_observed": True,
    }
    assert route["blocker_combinations"] == [
        {"blockers": ["gate_absent", "regime_blocked"], "evaluations": 12}
    ]
    path = route["one_blocker_paths"][0]
    assert path["horizon_minutes"] == 30
    assert path["independent_resolved"] == 3
    assert path["mean_after_estimated_friction_bps"] == 8.0
    assert path["mean_excluding_largest_bps"] == 2.0
    assert path["assessment"] == "robust_report_only_research_lead"
    assert report["robust_report_only_leads"] == [path]
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["automatic_live_change"] is False


def test_diagnostics_keep_seed_only_route_explicitly_unavailable() -> None:
    """A configured route without a completed outcome must remain visible."""
    audit = _audit()
    readiness = audit["readiness"]["by_provider_symbol"]
    readiness["slow|BTC"] = {
        "count": 1,
        "eligible": 0,
        "latest_fraction": 0.25,
        "latest_blockers": ["pre_activation_readiness_seed"],
        "blockers": {"pre_activation_readiness_seed": 1},
        "blocker_combinations": [
            {"blockers": ["pre_activation_readiness_seed"], "evaluations": 1}
        ],
    }
    scorecard = audit["strategy_scorecard"]["by_provider_symbol"]
    scorecard["slow|BTC"] = {"historical_cadence": "weekly"}

    routes = {
        route["route"]: route
        for route in build_live_opportunity_diagnostics(audit)["routes"]
    }

    route = routes["slow|BTC"]
    assert route["signal_outcomes_status"] == (
        "unavailable_no_completed_route_evaluation"
    )
    assert route["outcome_evaluations"] == 0
    assert route["eligible_evaluations"] == 0
    assert route["scarcity_interpretation"] == "no_completed_route_evaluations"
    assert route["one_blocker_paths"] == []
    assert route["readiness_evaluations"] == 1
    assert route["latest_blockers"] == ["pre_activation_readiness_seed"]


def test_diagnostics_label_legacy_side_coverage_unavailable() -> None:
    """An older valid audit may omit side counts without inventing coverage."""
    audit = _audit()
    del audit["signal_outcomes"]["by_provider_symbol"]["strategy|SOL"]["by_side"]

    route = build_live_opportunity_diagnostics(audit)["routes"][0]

    assert route["decision_side_coverage"] == {
        "status": "unavailable_legacy_audit",
        "by_side": {},
        "directional_evaluations": None,
        "nondirectional_evaluations": None,
        "observed_sides": [],
        "eligible_sides": [],
        "both_sides_observed": False,
    }


def test_diagnostics_distinguish_nondirectional_evaluations() -> None:
    """Completed no-direction rows must not be mislabeled as side coverage."""
    audit = _audit()
    outcomes = audit["signal_outcomes"]["by_provider_symbol"]["strategy|SOL"]
    outcomes["evaluations"] = 14
    outcomes["no_direction"] = 2

    coverage = build_live_opportunity_diagnostics(audit)["routes"][0][
        "decision_side_coverage"
    ]

    assert coverage["directional_evaluations"] == 12
    assert coverage["nondirectional_evaluations"] == 2
    assert coverage["observed_sides"] == ["long", "short"]


def test_diagnostics_reject_outcome_route_outside_configured_scope() -> None:
    """Unknown outcome identities must not be accepted as configured routes."""
    audit = _audit()
    outcomes = audit["signal_outcomes"]["by_provider_symbol"]
    outcomes["unknown|BTC"] = _route_outcomes()

    with pytest.raises(ValueError, match="outcome route scope"):
        build_live_opportunity_diagnostics(audit)


def test_diagnostics_reject_readiness_scorecard_scope_mismatch() -> None:
    """Configured readiness and scorecard identities must remain exact."""
    audit = _audit()
    audit["readiness"]["by_provider_symbol"]["slow|BTC"] = {
        "count": 0,
        "latest_fraction": 0.0,
        "latest_blockers": [],
        "blockers": {},
        "blocker_combinations": [],
    }

    with pytest.raises(ValueError, match="configured route scope"):
        build_live_opportunity_diagnostics(audit)


def test_diagnostics_keep_sparse_or_negative_paths_out_of_robust_leads() -> None:
    """One extreme or negative independent path is diagnostic, not a proposal."""
    audit = _audit()
    blocker = audit["signal_outcomes"]["by_provider_symbol"]["strategy|SOL"]
    horizons = blocker["one_blocker_near_misses"]["by_blocker"]["gate_absent"]
    independent = horizons["horizons"]["30"]["independent_opportunity_capture"]
    independent["resolved"] = 1
    independent["mean_excluding_largest_close_after_estimated_friction_bps"] = None

    report = build_live_opportunity_diagnostics(audit)

    path = report["routes"][0]["one_blocker_paths"][0]
    assert path["assessment"] == "insufficient_independent_paths"
    assert report["robust_report_only_leads"] == []


def test_closed_hypothesis_removes_matching_path_from_robust_leads() -> None:
    """A rejected exact blocker relaxation cannot reappear as a research lead."""
    decision = {
        "hypothesis_id": "closed-gate",
        "route": "strategy|SOL",
        "experiment": "remove_gate",
        "status": "rejected",
        "decision_reason": "the preregistered exact replay lost after costs",
        "decision_source": "closed-gate.json",
        "reopen_condition": "a distinct preregistered causal window",
        "execution_effect": "report_only",
        "closed_live_diagnostic_blockers": ["gate_absent"],
    }

    report = build_live_opportunity_diagnostics(
        _audit(), hypothesis_decisions=[decision]
    )

    path = report["routes"][0]["one_blocker_paths"][0]
    assert path["raw_assessment"] == "robust_report_only_research_lead"
    assert path["assessment"] == "closed_by_hypothesis_decision"
    assert path["hypothesis_disposition"] == {
        "hypothesis_id": "closed-gate",
        "status": "rejected",
        "decision_source": "closed-gate.json",
        "reopen_condition": "a distinct preregistered causal window",
    }
    assert report["robust_report_only_leads"] == []


def test_diagnostics_rank_episode_onsets_not_repeated_blocker_rows() -> None:
    """Persistent blocker rows must not manufacture a robust research lead."""
    audit = _audit()
    audit["signal_outcomes"]["portfolio_opportunity_dedup"] = {
        "by_attribution": [
            {
                "symbol": "SOL",
                "providers": [{"strategy_id": "strategy", "blocker": "gate_absent"}],
                "horizons": {
                    "30": {
                        "episode_onsets": {
                            "missing_data": 0,
                            "censored": 0,
                            "independent_opportunity_capture": {
                                "resolved": 3,
                                "mean_close_after_estimated_friction_bps": 4.0,
                                "mean_excluding_largest_close_after_estimated_friction_bps": -1.0,
                                "cost_clearing_close_rate": 2.0 / 3.0,
                            },
                        }
                    }
                },
            }
        ]
    }

    report = build_live_opportunity_diagnostics(audit)

    path = report["routes"][0]["one_blocker_paths"][0]
    assert path["mean_after_estimated_friction_bps"] == 4.0
    assert path["mean_excluding_largest_bps"] == -1.0
    assert path["assessment"] == "negative_or_concentrated_after_estimated_friction"
    assert report["robust_report_only_leads"] == []


def test_diagnostics_reject_ambiguous_episode_attribution() -> None:
    """Route-level ranking must not pool separate side episode summaries."""
    audit = _audit()
    attribution = {
        "symbol": "SOL",
        "providers": [{"strategy_id": "strategy", "blocker": "gate_absent"}],
        "horizons": {"30": {"episode_onsets": _episode_onset_capture()}},
    }
    audit["signal_outcomes"]["portfolio_opportunity_dedup"] = {
        "by_attribution": [
            dict(attribution, side="long"),
            dict(attribution, side="short"),
        ]
    }

    report = build_live_opportunity_diagnostics(audit)

    path = report["routes"][0]["one_blocker_paths"][0]
    assert path["sample_basis"] == "side_separated_episode_evidence"
    assert path["episode_attribution_count"] == 2
    assert path["assessment"] == "side_separation_required"
    assert report["robust_report_only_leads"] == []


def test_diagnostics_censor_multi_provider_episode_attribution() -> None:
    """Shared-symbol episodes must not freeze every route diagnostic."""
    audit = _audit()
    audit["signal_outcomes"]["portfolio_opportunity_dedup"] = {
        "by_attribution": [
            {
                "symbol": "SOL",
                "side": "long",
                "providers": [
                    {"strategy_id": "strategy", "blocker": "gate_absent"},
                    {"strategy_id": "other", "blocker": "other_gate"},
                ],
                "horizons": {"30": {"episode_onsets": _episode_onset_capture()}},
            }
        ]
    }

    report = build_live_opportunity_diagnostics(audit)

    path = report["routes"][0]["one_blocker_paths"][0]
    assert path["sample_basis"] == "portfolio_attribution_ambiguous"
    assert path["episode_attribution_count"] == 0
    assert path["ambiguous_episode_attribution_count"] == 1
    assert path["assessment"] == "portfolio_attribution_ambiguous"
    assert report["robust_report_only_leads"] == []


def test_diagnostics_distinguish_current_execution_from_frozen_cadence() -> None:
    """A resolved live lifecycle must supersede stale current-outcome wording."""
    audit = _audit()
    score = audit["strategy_scorecard"]["by_provider_symbol"]["strategy|SOL"]
    score.update(_resolved_short_score())

    route = build_live_opportunity_diagnostics(audit)["routes"][0]

    assert route["historical_cadence"] == "42 trades / 201 days"
    assert route["historical_cadence_currentness"] == (
        "superseded_by_current_live_execution"
    )
    assert route["current_live_execution"] == {
        "status": "resolved_lifecycles_available",
        "closed_lifecycles": 1,
        "observed_sides": ["short"],
        "wins": 1,
        "losses": 0,
        "breakeven": 0,
        "net_pnl_usd": 21.355552,
        "fees_usd": 0.855709,
        "funding_usd": 0.0,
        "net_return_on_margin_pct": 4.222156379857299,
        "largest_winner_share_of_gross_profit_pct": 100.0,
        "net_pnl_excluding_largest_winner_usd": 0.0,
    }


def test_diagnostics_surface_poll_normalized_blocker_episodes() -> None:
    """Raw poll counts and contiguous blocker episodes must remain distinct."""
    audit = _audit()
    readiness = audit["readiness"]["by_provider_symbol"]["strategy|SOL"]
    readiness["readiness_sampling_basis"] = "backend_poll_evaluations"
    readiness["blocker_episode_basis"] = "maximal_consecutive_identical_blocker_sets"
    readiness["blocker_episode_combinations"] = [
        {"blockers": ["gate_absent"], "episodes": 1, "evaluations": 12}
    ]

    route = build_live_opportunity_diagnostics(audit)["routes"][0]

    assert route["readiness_sampling_basis"] == "backend_poll_evaluations"
    assert route["blocker_episode_status"] == "available"
    assert route["blocker_episode_combinations"] == [
        {"blockers": ["gate_absent"], "episodes": 1, "evaluations": 12}
    ]


def _audit() -> dict[str, object]:
    return {
        "run": {
            "first_observed_at_utc": "2026-08-13T21:00:00+00:00",
            "last_observed_at_utc": "2026-08-13T22:00:00+00:00",
        },
        "readiness": {
            "by_provider_symbol": {
                "strategy|SOL": {
                    "count": 12,
                    "eligible": 0,
                    "latest_fraction": 0.5,
                    "latest_blockers": ["gate_absent"],
                    "blockers": {"gate_absent": 12},
                    "blocker_combinations": [
                        {
                            "blockers": ["gate_absent", "regime_blocked"],
                            "evaluations": 12,
                        }
                    ],
                }
            }
        },
        "strategy_scorecard": {
            "by_provider_symbol": {
                "strategy|SOL": {"historical_cadence": "42 trades / 201 days"}
            }
        },
        "signal_outcomes": {
            "evaluations": 12,
            "eligible_evaluations": 0,
            "directional_evaluations": 12,
            "coverage": {"right_censored_observations": 7},
            "by_provider_symbol": {"strategy|SOL": _route_outcomes()},
        },
    }


def _route_outcomes() -> dict[str, object]:
    return {
        "evaluations": 12,
        "by_side": {
            "long": {"evaluations": 8, "eligible_evaluations": 0},
            "short": {"evaluations": 4, "eligible_evaluations": 0},
        },
        "no_direction": 0,
        "by_evidence_class": {"eligible_signal": {"evaluations": 0}},
        "one_blocker_near_misses": {
            "by_blocker": {
                "gate_absent": {
                    "evaluations": 4,
                    "horizons": {"30": _horizon()},
                }
            }
        },
    }


def _resolved_short_score() -> dict[str, object]:
    return {
        "execution_outcomes_identifiable": True,
        "execution_performance": {
            "closed_trades": 1,
            "wins": 1,
            "losses": 0,
            "breakeven": 0,
            "net_pnl_usd": 21.355552,
            "fees_usd": 0.855709,
            "funding_usd": 0.0,
            "net_return_on_margin_pct": 4.222156379857299,
        },
        "execution_performance_by_side": {"short": {"closed_trades": 1}},
        "repeatability_evidence": {
            "largest_winner_share_of_gross_profit_pct": 100.0,
            "net_pnl_excluding_largest_winner_usd": 0.0,
        },
    }


def _horizon() -> dict[str, object]:
    return {
        "independent_opportunity_capture": {
            "resolved": 3,
            "mean_close_after_estimated_friction_bps": 8.0,
            "mean_excluding_largest_close_after_estimated_friction_bps": 2.0,
            "cost_clearing_close_rate": 2.0 / 3.0,
        },
        "censored": 1,
        "missing_data": 0,
    }


def _episode_onset_capture() -> dict[str, object]:
    return {
        "missing_data": 0,
        "censored": 0,
        "independent_opportunity_capture": {
            "resolved": 3,
            "mean_close_after_estimated_friction_bps": 4.0,
            "mean_excluding_largest_close_after_estimated_friction_bps": -1.0,
            "cost_clearing_close_rate": 2.0 / 3.0,
        },
    }
