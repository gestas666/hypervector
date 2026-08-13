"""Chronological fold tests for the sweep development experiment."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from hypervector.research.liquidity_sweep_experiment import (
    assign_development_folds,
    build_development_folds,
)


def test_development_folds_have_one_day_purges() -> None:
    """Neighboring folds cannot share adjacent lifecycle decisions."""
    folds = build_development_folds(
        datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 4, 1, tzinfo=UTC)
    )

    assert folds[1].start_utc - folds[0].end_utc == pd.Timedelta(days=1)
    assert folds[2].start_utc - folds[1].end_utc == pd.Timedelta(days=1)


def test_fold_assignment_rejects_boundary_crossing_lifecycle() -> None:
    """An outcome crossing a fold boundary is excluded from evidence."""
    folds = build_development_folds(
        datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 4, 1, tzinfo=UTC)
    )
    entry = folds[0].end_utc - pd.Timedelta(hours=1)
    outcomes = pd.DataFrame(
        {
            "entry_time_utc": [entry],
            "outcome_time_utc": [entry + pd.Timedelta(hours=2)],
            "accepted": [True],
            "displacement_reason": [None],
        }
    )

    assigned = assign_development_folds(outcomes, folds)

    assert assigned.iloc[0]["fold_id"] == 0
    assert not bool(assigned.iloc[0]["accepted"])
    assert assigned.iloc[0]["displacement_reason"] == "purge_or_fold_boundary"
