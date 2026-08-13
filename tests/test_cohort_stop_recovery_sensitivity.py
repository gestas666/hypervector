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
