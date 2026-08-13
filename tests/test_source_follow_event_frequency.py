"""Causal event-frequency contracts for the frozen source-follow policy."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.source_follow_event_frequency import (
    SourceFollowFrequencyPolicy,
    audit_source_follow_event_frequency,
)


def _inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.date_range("2026-07-01", periods=6, freq="5min", tz="UTC")
    labels = pd.DataFrame(
        {
            "available_at": index + pd.Timedelta(minutes=5),
            "primary_code": [
                "RANGE",
                "TREND_DOWN",
                "RANGE",
                "TREND_UP",
                "RANGE",
                "BREAKOUT",
            ],
            "secondary_code": [None, None, None, None, None, "BK_UPWARD"],
            "confidence": [0.8] * 6,
        },
        index=index,
    )
    ranges = [20.0, 20.0, 20.0, 10.0, 20.0, 20.0]
    bars = pd.DataFrame(
        {
            "open": [100.0] * 6,
            "high": [100.0 + value / 100.0 for value in ranges],
            "low": [100.0] * 6,
            "close": [100.0] * 6,
            "volume": [1.0] * 6,
        },
        index=index,
    )
    return labels, bars


def test_frequency_audit_counts_sides_and_range_exclusions() -> None:
    labels, bars = _inputs()

    report = audit_source_follow_event_frequency(
        labels,
        bars,
        SourceFollowFrequencyPolicy(),
        trailing_days=(7,),
    )

    assert report["source_events_before_range"] == 3
    assert report["eligible_events"] == 2
    assert report["excluded_below_minimum_range"] == 1
    assert report["excluded_above_maximum_range"] == 0
    assert report["by_direction"] == {"long": 1, "short": 1}
    assert report["by_primary"] == {"BREAKOUT": 1, "TREND_DOWN": 1}
    assert report["trailing"]["7"] == {
        "events": 2,
        "long": 1,
        "short": 1,
    }
    assert report["gap_hours"]["median"] == pytest.approx(1 / 3)


def test_frequency_audit_does_not_invent_onset_at_left_boundary() -> None:
    labels, bars = _inputs()
    labels.loc[:, "primary_code"] = "TREND_DOWN"

    report = audit_source_follow_event_frequency(
        labels,
        bars,
        SourceFollowFrequencyPolicy(),
        trailing_days=(7,),
    )

    assert report["source_events_before_range"] == 0
    assert report["eligible_events"] == 0
    assert report["gap_hours"]["median"] is None


def test_frequency_audit_rejects_duplicate_trailing_windows() -> None:
    labels, bars = _inputs()

    with pytest.raises(ValueError, match="unique"):
        audit_source_follow_event_frequency(
            labels,
            bars,
            SourceFollowFrequencyPolicy(),
            trailing_days=(7, 7),
        )
