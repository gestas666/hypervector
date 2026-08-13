"""Tests for paired Recipe C direction evidence and overlap accounting."""

from __future__ import annotations

from copy import deepcopy

import pandas as pd
import pytest

from hypervector.research.hypertrader_direction_selector import (
    add_interval_uniqueness,
    consensus_direction_labels,
    pair_direction_outcomes,
)


def _outcome(
    decision: str,
    status: str,
    *,
    side: str,
    outcome: str | None = None,
) -> dict[str, object]:
    lifecycle = None
    admission = "not_submitted"
    if status != "not_submitted":
        admission = "submitted"
        lifecycle = {
            "direction": side,
            "status": status,
            "outcome_time_utc": outcome or "2026-07-01T00:10:00+00:00",
        }
    return {
        "decision_time_utc": decision,
        "label_time_utc": pd.Timestamp(decision) - pd.Timedelta(minutes=5),
        "admission": admission,
        "lifecycle": lifecycle,
    }


def _artifact(
    family: str,
    side: str,
    statuses: list[str],
    *,
    fill: str = "touch",
) -> dict[str, object]:
    decisions = [f"2026-07-01T00:{minute:02d}:00+00:00" for minute in (5, 15, 25)]
    outcomes = [
        _outcome(decision, status, side=side)
        for decision, status in zip(decisions, statuses, strict=True)
    ]
    return {
        "report_only": True,
        "runtime_strategy_changed": False,
        "candidate_family": family,
        "fill_rule": fill,
        "initial_equity": 10_000.0,
        "allocation_fraction": 0.7,
        "leverage": 40.0,
        "gross_margin_target_pct": 8.0,
        "entry_ttl_seconds": 60.0,
        "model_authority": "observe",
        "source_evidence": {"labels": {"sha256": "labels-sha"}},
        "development": {"events": 3, "event_outcomes": outcomes},
    }


def test_pair_direction_outcomes_classifies_ties_and_path_dependence() -> None:
    fade = _artifact(
        "source-fade-only",
        "long",
        ["target_completed", "liquidated", "not_submitted"],
    )
    follow = _artifact(
        "source-follow-only",
        "short",
        ["target_completed", "target_completed", "canceled"],
    )

    rows = pair_direction_outcomes(fade, follow)

    assert rows["preference"].tolist() == [
        "ambiguous",
        "follow",
        "path_dependent",
    ]
    assert rows["trainable"].tolist() == [False, True, False]


def test_pair_direction_outcomes_rejects_unequal_contracts() -> None:
    fade = _artifact("source-fade-only", "long", ["canceled"] * 3)
    follow = _artifact("source-follow-only", "short", ["canceled"] * 3)
    follow["leverage"] = 25.0

    with pytest.raises(ValueError, match="execution contracts differ"):
        pair_direction_outcomes(fade, follow)


def test_pair_direction_outcomes_rejects_timestamp_drift() -> None:
    fade = _artifact("source-fade-only", "long", ["canceled"] * 3)
    follow = _artifact("source-follow-only", "short", ["canceled"] * 3)
    follow_rows = follow["development"]["event_outcomes"]
    follow_rows[0]["decision_time_utc"] = "2026-07-01T00:06:00+00:00"

    with pytest.raises(ValueError, match="decision timestamps differ"):
        pair_direction_outcomes(fade, follow)


def test_add_interval_uniqueness_measures_overlap_without_row_inflation() -> None:
    rows = pd.DataFrame(
        {
            "signal_ts_ms": [0, 0, 20],
            "outcome_ts_ms": [10, 10, 30],
            "trainable": [True, True, True],
        }
    )

    weighted, summary = add_interval_uniqueness(rows)

    assert weighted["average_uniqueness"].tolist() == [0.5, 0.5, 1.0]
    assert summary == {
        "nominal_trainable": 3,
        "effective_sample_size": 2.0,
        "mean_uniqueness": 2.0 / 3.0,
    }


def test_consensus_requires_every_fill_to_resolve_the_same_direction() -> None:
    base = pd.DataFrame(
        {
            "decision_time_utc": pd.to_datetime(
                ["2026-07-01T00:05:00Z", "2026-07-01T00:15:00Z"], utc=True
            ),
            "signal_ts_ms": [100, 200],
            "outcome_ts_ms": [150, 250],
            "preference": ["follow", "fade"],
        }
    )
    second = deepcopy(base)
    third = deepcopy(base)
    third.loc[1, "preference"] = "ambiguous"

    rows = consensus_direction_labels(
        {"touch": base, "through": second, "trade-through": third}
    )

    assert rows["consensus_direction"].tolist() == ["follow", "unresolved"]
    assert rows["direction_label"].tolist() == [1, pd.NA]
    assert rows["trainable"].tolist() == [True, False]
