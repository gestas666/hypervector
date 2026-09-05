"""Reporting tests for the HIP-3 cash-open gap reversal."""

from __future__ import annotations

from hypervector.research.hip3_cash_open_gap_reversal_candidate import (
    evaluate_hip3_cash_open_gap_reversal_development,
)
from hypervector.research.hip3_cash_open_gap_reversal_reporting import (
    build_hip3_cash_open_gap_reversal_report,
)
from hip3_cash_open_gap_reversal_fixtures import archive_bars, execution


def test_report_exposes_robustness_and_zero_live_authority() -> None:
    """Serialize both-side economics, technical paths, and sealed OOS."""
    bars, windows = archive_bars()
    result = evaluate_hip3_cash_open_gap_reversal_development(
        bars, execution(), windows=windows
    )
    report = build_hip3_cash_open_gap_reversal_report(
        result,
        bars.loc[bars.index < windows.development_end_utc],
        {"hypothesis_id": "cost-fixture"},
    )
    economics = report["development_economics"]
    checks = report["research_disposition"]["checks"]
    assert report["schema_version"] == "hip3_cash_open_gap_reversal_development_v1"
    assert report["execution_authority"] == "none"
    assert report["automatic_promotion"] is False
    assert report["validation_accessed"] is False
    assert report["holdout_accessed"] is False
    assert economics["stress"]["completed_trades"] == 3
    assert economics["stress"]["diagnostics"]["long"]["trades"] == 1
    assert economics["stress"]["diagnostics"]["short"]["trades"] == 2
    assert checks["both_directions_observed"]
    assert checks["stress_positive_without_largest_winner"]
    assert report["technical_path_evidence"]["status"] == "resolved"


def test_report_identifies_exact_unresolved_entry_bar_without_opening_oos() -> None:
    """Bind one failed entry slice to its exact development lifecycle and bar."""
    bars, windows = archive_bars()
    entry_bar = bars.index.get_loc("2026-06-09T13:45:00Z")
    bars.iloc[entry_bar, bars.columns.get_loc("entry_mark_path_complete")] = False
    bars.iloc[entry_bar, bars.columns.get_loc("entry_maximum_mark_interval_ms")] = (
        6000.0
    )
    result = evaluate_hip3_cash_open_gap_reversal_development(
        bars, execution(), windows=windows
    )

    report = build_hip3_cash_open_gap_reversal_report(
        result,
        bars.loc[bars.index < windows.development_end_utc],
        {"hypothesis_id": "cost-fixture"},
    )

    detail = report["technical_path_detail"]
    assert detail["qualification_authority"] == "none"
    assert detail["validation_accessed"] is False
    assert len(detail["nominal"]["unresolved_lifecycles"]) == 1
    assert detail["nominal"]["unresolved_full_path_bars"] == []
    assert detail["nominal"]["unresolved_entry_slice_bars"] == [
        {
            "bar_open_utc": "2026-06-09T13:45:00+00:00",
            "entry_slice_unresolved": True,
            "full_mark_path_unresolved": False,
            "mark_snapshot_count": 100,
            "maximum_mark_interval_ms": 100.0,
            "entry_mark_snapshot_count": 100,
            "entry_maximum_mark_interval_ms": 6000.0,
        }
    ]
    assert detail["nominal"]["unresolved_union_bar_count"] == 1
    assert detail["nominal"]["unresolved_full_path_bar_count"] == 0
    assert detail["nominal"]["unresolved_entry_slice_bar_count"] == 1


def test_report_separates_full_path_and_entry_slice_bar_sets() -> None:
    """Do not collapse full-lifecycle and entry-slice path failures."""
    bars, windows = archive_bars()
    entry_bar = bars.index.get_loc("2026-06-09T13:45:00Z")
    carried_bar = bars.index.get_loc("2026-06-09T14:00:00Z")
    bars.iloc[entry_bar, bars.columns.get_loc("entry_mark_path_complete")] = False
    bars.iloc[entry_bar, bars.columns.get_loc("risk_low")] = 100.85
    bars.iloc[entry_bar, bars.columns.get_loc("risk_entry_low")] = 100.85
    bars.iloc[entry_bar, bars.columns.get_loc("risk_high")] = 101.0
    bars.iloc[entry_bar, bars.columns.get_loc("risk_entry_high")] = 101.0
    bars.iloc[carried_bar, bars.columns.get_loc("risk_low")] = 99.9
    bars.iloc[carried_bar, bars.columns.get_loc("mark_path_complete")] = False
    result = evaluate_hip3_cash_open_gap_reversal_development(
        bars, execution(), windows=windows
    )

    report = build_hip3_cash_open_gap_reversal_report(
        result,
        bars.loc[bars.index < windows.development_end_utc],
        {"hypothesis_id": "cost-fixture"},
    )

    detail = report["technical_path_detail"]["nominal"]
    assert [row["bar_open_utc"] for row in detail["unresolved_entry_slice_bars"]] == [
        "2026-06-09T13:45:00+00:00"
    ]
    assert [row["bar_open_utc"] for row in detail["unresolved_full_path_bars"]] == [
        "2026-06-09T14:00:00+00:00"
    ]
    assert detail["unresolved_union_bar_count"] == 2
