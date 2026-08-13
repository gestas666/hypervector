from dataclasses import replace

import pytest

from hypervector.research.cohort_forward_one_blocker_challenger import (
    ForwardOneBlockerChallengerSpec,
    build_forward_challenger_report,
)


def test_forward_report_keeps_both_sides_and_no_execution_authority() -> None:
    spec = _spec()
    report = build_forward_challenger_report(_replay(spec), spec=spec)

    assert report["contract"]["report_only"] is True
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["automatic_promotion"] is False
    assert report["contract"]["cutoff_time_ms"] == 1_785_862_320_000
    assert report["contract"]["execution"]["minimum_entry_spacing_minutes"] == 60
    assert report["state"] == "descriptive_resolved_forward_evidence"
    assert report["summary"] == {
        "resolved": 2,
        "wins": 1,
        "losses": 1,
        "total_net_return_bps": pytest.approx(20.0),
        "mean_net_return_bps": pytest.approx(10.0),
        "profit_factor": pytest.approx(2.0),
        "largest_abs_contribution_fraction": pytest.approx(2.0 / 3.0),
        "stop_proxy_crosses": 1,
        "long_resolved": 1,
        "short_resolved": 1,
    }
    assert len(report["latest_executions"]) == 2


def test_forward_report_rejects_a_replay_from_before_the_frozen_cutoff() -> None:
    spec = _spec()
    replay = _replay(spec)
    replay["contract"]["minimum_available_time_ms"] = 0

    with pytest.raises(ValueError, match="frozen forward contract"):
        build_forward_challenger_report(replay, spec=spec)


def test_forward_spec_accepts_a_frozen_report_only_opposed_cohort() -> None:
    spec = replace(_spec(), opi_cohort="opposed")

    assert spec.execution_contract().opi_cohort == "opposed"


def test_forward_spec_rejects_an_unknown_execution_cohort() -> None:
    with pytest.raises(ValueError, match="OPI cohort"):
        replace(_spec(), opi_cohort="neutral")  # type: ignore[arg-type]


def test_forward_spec_preserves_a_longer_prospective_reentry_buffer() -> None:
    spec = replace(_spec(), minimum_entry_spacing_minutes=75)

    assert spec.execution_contract().entry_spacing_minutes == 75
    assert spec.execution_contract().horizon_minutes == 60


def test_forward_report_identifies_an_observe_only_signal_source() -> None:
    """A research-only source must remain explicit in the published contract."""
    spec = replace(_spec(), source_authority="observe_only")

    report = build_forward_challenger_report(_replay(spec), spec=spec)

    assert report["contract"]["source_signal_authority"] == "observe_only"


def test_forward_spec_preserves_a_predeclared_target_proxy() -> None:
    """A prospective target challenger carries its fixed target into replay."""
    spec = replace(_spec(), target_proxy_bps=20.0)

    assert spec.execution_contract().target_proxy_bps == 20.0
    assert spec.execution_contract().as_payload()["target_proxy_bps"] == 20.0


def test_forward_report_rejects_target_contract_drift() -> None:
    """A target-enabled forward window cannot accept a no-target replay."""
    spec = replace(_spec(), target_proxy_bps=20.0)
    replay = _replay(spec)
    replay["contract"]["target_proxy_bps"] = None

    with pytest.raises(ValueError, match="frozen forward contract"):
        build_forward_challenger_report(replay, spec=spec)


def test_target_report_exposes_fee_adjusted_bracket_geometry() -> None:
    """The live journal must make asymmetric target/stop economics explicit."""
    spec = replace(_spec(), target_proxy_bps=20.0)

    report = build_forward_challenger_report(_replay(spec), spec=spec)

    assert report["payoff_geometry"] == {
        "scope": "binary_target_stop_benchmark_before_funding",
        "execution_authority": "none",
        "performance_gate": False,
        "target_proxy_bps": 20.0,
        "stop_proxy_bps": 80.0,
        "estimated_round_trip_fee_bps": pytest.approx(8.64),
        "estimated_target_net_bps": pytest.approx(11.36),
        "estimated_stop_net_bps": pytest.approx(-88.64),
        "break_even_target_rate_pct": pytest.approx(88.64),
        "fixed_horizon_changes_realized_distribution": True,
    }


def test_forward_report_stratifies_untuned_five_minute_regime_context() -> None:
    """Regime context is descriptive and retains missing-feature coverage."""
    spec = _spec()
    replay = _replay(spec)
    executions = replay["executions"]
    assert isinstance(executions, list)
    executions[0]["entry_features"] = {"state_5m": "TREND_UP"}
    executions[1]["entry_features"] = {"state_5m": "TREND_UP"}

    report = build_forward_challenger_report(replay, spec=spec)

    context = report["entry_context_summary"]
    assert context["coverage"] == {
        "resolved": 2,
        "state_5m_observed": 2,
        "state_5m_missing": 0,
    }
    assert context["by_directional_stance"]["aligned"]["resolved"] == 1
    assert context["by_directional_stance"]["aligned"]["total_net_return_bps"] == 40.0
    assert context["by_directional_stance"]["opposed"]["resolved"] == 1
    assert context["by_directional_stance"]["opposed"]["total_net_return_bps"] == -20.0


def test_forward_report_stratifies_untuned_fifteen_minute_context() -> None:
    """HTF context remains descriptive and preserves directional stance."""
    spec = _spec()
    replay = _replay(spec)
    executions = replay["executions"]
    assert isinstance(executions, list)
    executions[0]["entry_features"] = {"context_15m": "TREND_UP"}
    executions[1]["entry_features"] = {"context_15m": "TREND_UP"}

    report = build_forward_challenger_report(replay, spec=spec)

    context = report["context_15m_summary"]
    assert context["mode"] == "untuned_fifteen_minute_regime_context"
    assert context["execution_authority"] == "none"
    assert context["performance_gate"] is False
    assert context["coverage"] == {
        "resolved": 2,
        "context_15m_observed": 2,
        "context_15m_missing": 0,
    }
    assert context["by_directional_stance"]["aligned"]["resolved"] == 1
    assert context["by_directional_stance"]["aligned"]["total_net_return_bps"] == 40.0
    assert context["by_directional_stance"]["opposed"]["resolved"] == 1
    assert context["by_directional_stance"]["opposed"]["total_net_return_bps"] == -20.0
    assert context["by_state_15m"]["TREND_UP"]["resolved"] == 2


def _spec() -> ForwardOneBlockerChallengerSpec:
    return ForwardOneBlockerChallengerSpec(
        strategy_id="hype_breakout_onset_bidirectional_v1",
        symbol="HYPE",
        blocker="5m_not_breakout",
        cutoff_time_ms=1_785_862_320_000,
        horizon_minutes=60,
        maximum_context_age_ms=30_000,
        maximum_entry_delay_ms=60_000,
        maximum_exit_delay_ms=30_000,
        notional_usd=25.0,
        taker_fee_rate=0.000432,
        stop_proxy_bps=80.0,
        opi_cohort="all",
    )


def _replay(spec: ForwardOneBlockerChallengerSpec) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "one_blocker_execution_feasibility",
        "contract": spec.execution_contract().as_payload(),
        "coverage": {
            "evaluations": 10,
            "pre_cutoff_excluded": 4,
            "exact_candidates": 2,
            "context_missing": 0,
            "context_stale": 0,
            "context_cohort_excluded": 0,
            "selected_non_overlapping": 2,
            "entry_missing": 0,
            "entry_capacity_failures": 0,
            "exit_missing": 0,
            "exit_capacity_failures": 0,
            "resolved_executions": 2,
        },
        "executions": [
            {
                "side": "long",
                "available_time_ms": spec.cutoff_time_ms + 1,
                "entry_time_ms": spec.cutoff_time_ms + 2,
                "exit_time_ms": spec.cutoff_time_ms + 3_600_002,
                "net_return_bps": 40.0,
                "crossed_stop_proxy": False,
            },
            {
                "side": "short",
                "available_time_ms": spec.cutoff_time_ms + 7_200_001,
                "entry_time_ms": spec.cutoff_time_ms + 7_200_002,
                "exit_time_ms": spec.cutoff_time_ms + 7_260_002,
                "net_return_bps": -20.0,
                "crossed_stop_proxy": True,
            },
        ],
        "by_side": {
            "long": {"resolved": 1},
            "short": {"resolved": 1},
        },
    }
