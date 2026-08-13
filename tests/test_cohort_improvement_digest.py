"""Contracts for portfolio-wide continuous-improvement telemetry."""

from __future__ import annotations

import pytest

import hypervector.research.cohort_improvement_digest as digest


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
            }
        },
    }

    report = digest.build_cohort_improvement_digest(
        _audit(), experiment_overrides=overrides
    )

    eth = next(row for row in report["experiment_queue"] if row["route"] == "eth|ETH")
    assert eth["next_experiment"] == "new_side_mechanic_version_required"
    assert eth["historical_assessment"] == "tested_side_timing_set_falsified"
    assert eth["execution_effect"] == "report_only"
    assert report["research_decision_overrides"]["applied_routes"] == ["eth|ETH"]


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
