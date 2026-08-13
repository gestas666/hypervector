"""Immutable-report projections for HIP-3 breakout-pressure research."""

from __future__ import annotations

from dataclasses import replace

from test_hip3_breakout_pressure_transfer import _asset, _config, _friction

from hypervector.research.hip3_breakout_pressure_reporting import (
    breakout_transfer_report,
    breakout_transfer_trades,
)
from hypervector.research.hip3_breakout_pressure_transfer import (
    run_hip3_breakout_pressure_transfer,
)


def test_report_accounts_for_every_trial_and_keeps_holdout_unread() -> None:
    result = run_hip3_breakout_pressure_transfer(
        (_asset(),),
        {"xyz:TEST": _friction()},
        configs=(_config(0.2), _config(0.9)),
    )

    report = breakout_transfer_report(result, source_evidence={"fixture": True})

    assert report["searched_trial_count"] == 2
    assert len(report["development_trials"]) == 2
    assert report["holdout"]["metrics_accessed"] is False
    assert report["execution_authority"] == "none"
    assert report["selection_policy"]["uses_validation"] is False
    assert report["source_evidence"] == {"fixture": True}


def test_trade_sidecar_labels_phase_symbol_and_friction() -> None:
    result = run_hip3_breakout_pressure_transfer(
        (_asset(),),
        {"xyz:TEST": _friction()},
        configs=(_config(0.2),),
    )
    frame = breakout_transfer_trades(result)

    assert {"phase", "symbol", "friction", "direction", "net_pnl_usd"}.issubset(
        frame.columns
    )
    assert set(frame["phase"]) <= {"development", "validation"}
    assert set(frame.loc[frame["phase"] == "validation", "friction"]) <= {
        "nominal",
        "stress",
    }


def test_reporting_rejects_any_claim_that_holdout_was_evaluated() -> None:
    result = run_hip3_breakout_pressure_transfer(
        (_asset(),),
        {"xyz:TEST": _friction()},
        configs=(_config(0.2),),
    )

    try:
        breakout_transfer_report(
            replace(result, holdout_status="evaluated"),
            source_evidence={},
        )
    except ValueError as exc:
        assert "sealed" in str(exc)
    else:
        raise AssertionError("report accepted an opened holdout")
