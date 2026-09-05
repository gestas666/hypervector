"""Reporting tests for the SPCX cash-open long exit challenger."""

from __future__ import annotations

from hypervector.research.hip3_cash_open_long_exit_challenger import (
    evaluate_cash_open_long_exit_challengers,
)
from hypervector.research.hip3_cash_open_long_exit_reporting import (
    build_cash_open_long_exit_report,
)
from hip3_cash_open_gap_reversal_fixtures import archive_bars, execution


def test_report_preserves_control_family_paths_and_zero_authority() -> None:
    """Expose every preregistered scenario without opening OOS economics."""
    bars, windows = archive_bars()
    result = evaluate_cash_open_long_exit_challengers(
        bars,
        execution("xyz:SPCX"),
        windows=windows,
        target_bps=(40.0, 60.0, 80.0),
    )

    report = build_cash_open_long_exit_report(
        result,
        bars.loc[bars.index < windows.development_end_utc],
        preregistration={"hypothesis_id": "fixture-preregistration"},
    )

    assert report["schema_version"] == "hip3_cash_open_long_exit_challenger_v1"
    assert report["execution_authority"] == "none"
    assert report["automatic_promotion"] is False
    assert report["validation_accessed"] is False
    assert report["holdout_accessed"] is False
    assert report["control"]["target_policy"] == "prior_cash_close"
    assert [row["target_bps"] for row in report["challengers"]] == [
        40.0,
        60.0,
        80.0,
    ]
    assert report["entry_identity_parity"]["status"] == "matched"
    assert report["entry_identity_parity"]["development_entries"] == 1
    assert all(
        row["technical_path"]["status"] == "resolved" for row in report["scenarios"]
    )
    assert report["live_change_proposed"] is False
