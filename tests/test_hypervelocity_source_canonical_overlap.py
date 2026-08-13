"""Tests for causal source-to-canonical regime overlap auditing."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hypervelocity_source_canonical_overlap import (
    align_source_events_to_canonical_decisions,
    summarize_source_canonical_overlap,
)


def _canonical_decisions() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=7, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "primary_regime": [
                "RANGE",
                "TREND_DOWN",
                "TREND_DOWN",
                "RANGE",
                "RANGE",
                "TREND_UP",
                "TREND_UP",
            ],
            "entry_direction": [None, "short", "short", None, None, "long", "long"],
            "state_1m": ["RANGE"] * 7,
            "state_5m": [
                "RANGE",
                "TREND_DOWN",
                "TREND_DOWN",
                "RANGE",
                "RANGE",
                "TREND_UP",
                "TREND_UP",
            ],
            "context_15m": ["TREND_UP"] * 7,
            "confidence": [0.5] * 7,
            "reason": ["test"] * 7,
        },
        index=index,
    )


def _source_events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "recipe_id": ["source", "source", "source"],
            "label_time_utc": pd.to_datetime(
                ["2026-01-01 00:01", "2026-01-01 00:06", "2026-01-01 00:10"],
                utc=True,
            ),
            "decision_time_utc": pd.to_datetime(
                ["2026-01-01 00:02", "2026-01-01 00:06", "2026-01-01 00:10"],
                utc=True,
            ),
            "side": ["short", "short", "short"],
            "confidence": [0.8, 0.9, 0.7],
        }
    )


def test_aligns_only_the_last_completed_one_minute_bar() -> None:
    aligned = align_source_events_to_canonical_decisions(
        _source_events(), _canonical_decisions()
    )

    assert aligned["canonical_bar_time_utc"].tolist() == [
        pd.Timestamp("2026-01-01 00:01", tz="UTC"),
        pd.Timestamp("2026-01-01 00:05", tz="UTC"),
        pd.Timestamp("2026-01-01 00:09", tz="UTC"),
    ]
    assert aligned["canonical_row_available"].tolist() == [True, True, False]
    assert aligned["canonical_entry_direction"].tolist()[:2] == ["short", "long"]
    assert aligned["entry_agreement"].tolist() == ["same", "opposite", "missing"]


def test_reports_nearest_canonical_short_onset_without_lookahead() -> None:
    aligned = align_source_events_to_canonical_decisions(
        _source_events(), _canonical_decisions()
    )

    assert aligned.loc[0, "nearest_same_side_onset_delta_minutes"] == 0.0
    assert aligned.loc[1, "nearest_same_side_onset_delta_minutes"] == -4.0
    assert pd.isna(aligned.loc[2, "nearest_same_side_onset_delta_minutes"])
    assert aligned.loc[0, "canonical_same_side_run_age_minutes"] == 0.0
    assert pd.isna(aligned.loc[1, "canonical_same_side_run_age_minutes"])
    assert pd.isna(aligned.loc[2, "canonical_same_side_run_age_minutes"])


def test_summarizes_agreement_and_onset_timing() -> None:
    aligned = align_source_events_to_canonical_decisions(
        _source_events(), _canonical_decisions()
    )

    summary = summarize_source_canonical_overlap(aligned)

    assert summary["events_total"] == 3
    assert summary["canonical_rows_available"] == 2
    assert summary["same_direction_entries"] == 1
    assert summary["opposite_direction_entries"] == 1
    assert summary["no_canonical_entry"] == 0
    assert summary["missing_canonical_rows"] == 1
    assert summary["same_direction_entry_rate_available"] == 0.5
    assert summary["same_side_onset_within_5m"] == 2
    assert summary["same_side_current_run_age_within_5m"] == 1
    assert summary["same_side_current_run_age_within_15m"] == 1
    assert summary["canonical_primary_regime_counts"] == {
        "TREND_DOWN": 1,
        "TREND_UP": 1,
    }


def test_rejects_naive_or_duplicate_canonical_index() -> None:
    events = _source_events()
    naive = _canonical_decisions()
    naive.index = naive.index.tz_localize(None)

    try:
        align_source_events_to_canonical_decisions(events, naive)
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("naive canonical index was accepted")

    duplicated = pd.concat([_canonical_decisions(), _canonical_decisions().iloc[[0]]])
    try:
        align_source_events_to_canonical_decisions(events, duplicated)
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("duplicate canonical index was accepted")
