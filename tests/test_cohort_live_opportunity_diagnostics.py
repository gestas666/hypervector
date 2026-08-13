"""Contracts for exact current-run signal-scarcity diagnostics."""

from __future__ import annotations

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
    assert route["scarcity_interpretation"] == (
        "zero_eligible_signal_observed_no_frequency_conclusion"
    )
    assert route["latest_blockers"] == ["gate_absent"]
    path = route["one_blocker_paths"][0]
    assert path["horizon_minutes"] == 30
    assert path["independent_resolved"] == 3
    assert path["mean_after_estimated_friction_bps"] == 8.0
    assert path["mean_excluding_largest_bps"] == 2.0
    assert path["assessment"] == "robust_report_only_research_lead"
    assert report["robust_report_only_leads"] == [path]
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["automatic_live_change"] is False


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
