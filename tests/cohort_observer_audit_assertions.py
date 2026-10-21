"""Shared assertions for the observer-audit baseline contract."""

from __future__ import annotations

from collections.abc import Mapping

_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_HULK = "test_trend_5m"
_RUN_ID = "observer-a"


def assert_observer_audit_baseline(report: Mapping[str, object]) -> None:
    """Assert the complete report-only observer baseline."""
    _assert_contract_and_runtime(report)
    _assert_signals_and_outcomes(report)
    _assert_readiness_and_learning(report)


def _assert_contract_and_runtime(report: Mapping[str, object]) -> None:
    assert report["observer_contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "orders_observed": False,
        "fills_observed": False,
        "profitability_measured": False,
        "performance_gate": False,
        "runtime_strategy_changed": False,
    }
    run = _mapping(report["run"])
    runtime = _mapping(report["runtime"])
    technical = _mapping(report["technical"])
    assert run["run_id"] == _RUN_ID
    assert run["symbols"] == list(_SYMBOLS)
    assert runtime["poll_cycles"] == 2
    assert runtime["routing_cycles"] == 2
    assert runtime["evaluation_cycles"] == 2
    assert technical["expected_provider_symbols"] == 8
    assert technical["initial_provider_symbols"] == 8
    assert technical["observed_provider_symbols"] == 8
    assert technical["technical_gaps"] == []
    assert technical["complete"] is True
    timing = _mapping(technical["decision_timing_seconds"])
    startup = _mapping(_mapping(timing["startup_seed_age_by_provider"])[_HULK])
    steady = _mapping(_mapping(timing["steady_state_arrival_lag_by_provider"])[_HULK])
    assert (startup["count"], startup["maximum"]) == (4, 2.0)
    assert (steady["count"], steady["maximum"]) == (4, 2.0)
    assert "arrival_lag_seconds_by_provider" not in technical


def _assert_signals_and_outcomes(report: Mapping[str, object]) -> None:
    signals = _mapping(report["signals"])
    assert signals["strategy_intents"] == 1
    assert signals["eligible_evaluations"] == 1
    assert signals["routed_actions"] == 0
    assert signals["withheld_reasons"] == {"observe_mode_no_execution": 1}
    outcomes = _mapping(report["signal_outcomes"])
    assert outcomes["contract"] == {
        "counterfactual_only": True,
        "fills_assumed": False,
        "pnl_claimed": False,
        "execution_authority": "none",
        "model_trained": False,
        "thresholds_selected": False,
        "configured_direction_attribution": "counterfactual_only",
        "path_start_policy": "first_full_minute_at_or_after_candidate_availability",
    }
    assert outcomes["preactivation_annotations_excluded"] == 8
    assert outcomes["evaluations"] == 8
    assert outcomes["eligible_evaluations"] == 1
    assert _mapping(outcomes["coverage"])["market_data_complete"] is True


def _assert_readiness_and_learning(report: Mapping[str, object]) -> None:
    readiness = _mapping(_mapping(report["readiness"])["by_provider_symbol"])
    hulk_btc = _mapping(readiness[f"{_HULK}|BTC"])
    assert hulk_btc["count"] == 2
    assert hulk_btc["first_fraction"] == 0.5
    assert hulk_btc["latest_fraction"] == 1.0
    assert hulk_btc["progressions"] == 1
    assert hulk_btc["regressions"] == 0
    assert hulk_btc["state_transitions"] == 1
    assert hulk_btc["latest_side"] == "long"
    assert report["learning"] == {
        "evidence_state": "setup_and_signal_paths_only_no_execution_outcomes",
        "signal_path_descriptives_identifiable": True,
        "strategy_edge_identifiable": False,
        "profitability_identifiable": False,
        "execution_quality_identifiable": False,
        "valid_uses": [
            "technical_parity",
            "signal_cadence",
            "setup_progression",
            "blocker_attribution",
        ],
    }


def _mapping(value: object) -> Mapping[str, object]:
    assert isinstance(value, Mapping)
    return value
