"""Report-only protective-stop recovery sensitivity tests."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_stop_recovery_sensitivity import (
    build_stop_recovery_sensitivity,
)


def _stopped_trade() -> dict[str, object]:
    return {
        "lifecycle_id": "xyz:SNDK:1",
        "source_run_id": "run-v39",
        "source_profile_fingerprint": "fingerprint-v39",
        "strategy_id": "hip3_breakout_pressure_v1",
        "symbol": "xyz:SNDK",
        "side": "long",
        "exit_reason": "protective_stop",
        "entry": {"price": 1_261.3, "size": 0.059},
        "exit": {"price": 1_249.2},
        "leverage": 5.0,
        "entry_margin_used_usd": 14.884,
        "entry_context": {
            "signal_provider": {"readiness": {"metrics": {"bar_range_bps": 40.0}}}
        },
        "protective_stop": {"trigger_price": 1_251.2096},
        "entry_followthrough_path": {
            "5": {
                "status": "resolved",
                "adverse_excursion_bps": 145.88,
                "directional_close_return_bps": 15.21,
            },
            "15": {
                "status": "resolved",
                "adverse_excursion_bps": 145.88,
                "directional_close_return_bps": 91.26,
            },
        },
        "post_exit_path": {
            "15": {
                "status": "resolved",
                "favorable_excursion_bps": 110.0,
                "directional_close_return_bps": 91.26,
            }
        },
    }


def test_wider_stop_reports_survival_without_claiming_execution() -> None:
    """A wider barrier reports observed survival, not a hypothetical fill."""
    report = build_stop_recovery_sensitivity(
        [_stopped_trade()], stop_widths_bps=(80.0, 100.0, 150.0)
    )

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_strategy_changes": False,
        "runtime_strategy_changed": False,
        "performance_gate": False,
    }
    trade = report["trades"][0]
    assert trade["actual_stop_width_bps"] == pytest.approx(80.0)
    assert trade["price_stop_distance_is_leverage_independent"] is True
    assert trade["control_barrier_loss_on_margin_pct"] == pytest.approx(4.0)
    assert trade["stop_distance_recent_bar_range_units"] == pytest.approx(2.0)
    assert trade["stop_distance_atr_units"] is None
    five = trade["horizons"]["5"]["candidates"]
    assert five["80bps"]["status"] == "barrier_crossed"
    assert five["100bps"]["status"] == "barrier_crossed"
    assert five["150bps"] == {
        "status": "survived_observed_path",
        "directional_close_return_bps": 15.21,
        "counterfactual_execution_pnl_available": False,
    }
    assert report["summary"]["protective_stop_trades"] == 1


def test_invalid_widths_fail_closed() -> None:
    """Candidate barriers must be positive, unique, and ordered."""
    with pytest.raises(ValueError, match="strictly increasing"):
        build_stop_recovery_sensitivity(
            [_stopped_trade()], stop_widths_bps=(100.0, 80.0)
        )


def test_assessment_horizon_keeps_candidate_dollar_risk_equal() -> None:
    """Wider barriers reduce notional instead of silently increasing risk."""
    trade = _stopped_trade()
    trade["entry_followthrough_path"]["15"]["adverse_excursion_bps"] = 120.0
    report = build_stop_recovery_sensitivity(
        [trade],
        stop_widths_bps=(80.0, 100.0, 150.0),
        assessment_horizon_minutes=15,
    )

    summary = report["summary"]["assessment"]
    candidates = summary["candidates"]
    assert summary["resolved_trades"] == 1
    assert summary["possible_control_whipsaws"] == 1
    assert summary["entry_recovered_after_stop"] == 1
    assert candidates["80bps"]["equal_risk_notional_usd"] == pytest.approx(
        1_261.3 * 0.059
    )
    assert candidates["150bps"]["equal_risk_notional_usd"] == pytest.approx(
        1_261.3 * 0.059 * 80.0 / 150.0
    )
    assert candidates["100bps"]["barrier_crossed"] == 1
    assert candidates["150bps"]["survived"] == 1
    assert candidates["150bps"]["equal_risk_gross_pnl_usd"] == pytest.approx(
        1_261.3 * 0.059 * 80.0 / 150.0 * 91.26 / 10_000.0
    )
    assert summary["counterfactual_net_pnl_available"] is False


def test_missing_assessment_horizon_is_censored_not_success_shaped() -> None:
    """Absent path evidence must not crash or count as a resolved outcome."""
    report = build_stop_recovery_sensitivity(
        [_stopped_trade()],
        stop_widths_bps=(80.0, 100.0),
        assessment_horizon_minutes=60,
    )

    assessment = report["summary"]["assessment"]
    assert assessment["resolved_trades"] == 0
    assert assessment["censored_trades"] == 1
    assert assessment["possible_control_whipsaws"] == 0
    assert assessment["candidates"]["80bps"] == {
        "status": "insufficient_path_evidence",
        "resolved_trades": 0,
        "barrier_crossed": 0,
        "survived": 0,
        "equal_risk_notional_usd": None,
        "equal_risk_gross_pnl_usd": None,
    }


def test_positive_close_without_post_stop_entry_recovery_is_not_whipsaw() -> None:
    """Whipsaw requires a post-stop entry recovery, not a later positive close."""
    trade = _stopped_trade()
    trade["post_exit_path"]["15"]["favorable_excursion_bps"] = 20.0

    report = build_stop_recovery_sensitivity(
        [trade],
        stop_widths_bps=(80.0, 100.0),
        assessment_horizon_minutes=15,
    )

    assessment = report["summary"]["assessment"]
    assert assessment["entry_recovered_after_stop"] == 0
    assert assessment["possible_control_whipsaws"] == 0
