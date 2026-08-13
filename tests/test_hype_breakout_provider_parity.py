"""Tests for historical-to-live HT-Breakout decision parity."""

from __future__ import annotations

import pytest

from hypervector.research.hype_breakout_provider_parity import (
    ParityEntry,
    compare_hype_breakout_entries,
)


def test_exact_entry_identity_and_reference_price_reports_parity() -> None:
    """Matching decision clocks, sides, and prices must produce exact parity."""
    historical = (
        ParityEntry(1_000, "long", 100.0),
        ParityEntry(2_000, "short", 101.0),
    )

    report = compare_hype_breakout_entries(historical, historical)

    assert report["exact_parity"] is True
    assert report["historical_entries"] == 2
    assert report["live_entries"] == 2
    assert report["missing_from_live"] == []
    assert report["extra_in_live"] == []
    assert report["reference_price_mismatches"] == []
    assert report["execution_authority"] == "none"
    assert report["runtime_strategy_changed"] is False


def test_mismatch_report_separates_identity_and_reference_failures() -> None:
    """The audit must expose omitted, extra, and price-shifted decisions."""
    historical = (
        ParityEntry(1_000, "long", 100.0),
        ParityEntry(2_000, "short", 101.0),
    )
    live = (
        ParityEntry(1_000, "long", 100.5),
        ParityEntry(3_000, "short", 102.0),
    )

    report = compare_hype_breakout_entries(historical, live)

    assert report["exact_parity"] is False
    assert report["missing_from_live"] == [
        {"decision_time_ms": 2_000, "side": "short", "reference_price": 101.0}
    ]
    assert report["extra_in_live"] == [
        {"decision_time_ms": 3_000, "side": "short", "reference_price": 102.0}
    ]
    assert report["reference_price_mismatches"] == [
        {
            "decision_time_ms": 1_000,
            "side": "long",
            "historical_reference_price": 100.0,
            "live_reference_price": 100.5,
            "absolute_difference": 0.5,
        }
    ]


def test_duplicate_decision_side_identity_is_rejected() -> None:
    """Duplicate identities cannot be collapsed into success-shaped parity."""
    duplicate = (
        ParityEntry(1_000, "long", 100.0),
        ParityEntry(1_000, "long", 100.0),
    )

    with pytest.raises(ValueError, match="duplicate historical"):
        compare_hype_breakout_entries(duplicate, ())
