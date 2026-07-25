"""Tests for replay-specific chronological model comparison."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.ml.replay_models import (
    REPLAY_FEATURE_NAMES,
    chronological_replay_folds,
    train_replay_candidates,
)


def _replay_rows(n_rows: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    entry = np.arange(n_rows, dtype=np.int64) * 3_600_000
    frame = pd.DataFrame(
        {
            "entry_ts_ms": entry,
            "exit_ts_ms": entry + 60_000,
            "direction": np.where(np.arange(n_rows) % 2 == 0, "long", "short"),
            "net_margin_pct": np.where(np.arange(n_rows) % 4 == 0, 1.0, -1.0),
        }
    )
    for name in REPLAY_FEATURE_NAMES:
        if name == "direction_sign":
            continue
        frame[name] = rng.normal(size=n_rows)
    return frame


def test_chronological_replay_folds_purge_overlapping_outcomes():
    """Training outcomes must resolve before each embargoed test window."""
    rows = _replay_rows()

    folds = chronological_replay_folds(rows, n_splits=3, embargo_minutes=30)

    assert folds
    for train, test in folds:
        assert rows.iloc[train]["exit_ts_ms"].max() < (
            rows.iloc[test]["entry_ts_ms"].min() - 30 * 60_000
        )


def test_train_replay_candidates_writes_both_model_options(tmp_path: Path):
    """LightGBM and temporal logistic candidates share chronological evidence."""
    result = train_replay_candidates(
        _replay_rows(),
        tmp_path / "candidate",
        n_splits=3,
        embargo_minutes=30,
    )

    assert result.lightgbm_path.is_file()
    assert result.temporal_logistic_path.is_file()
    assert result.lagged_logistic_path.is_file()
    assert result.metadata_path.is_file()
    assert result.metrics["lightgbm"]["folds_used"] > 0
    assert result.metrics["temporal_logistic"]["folds_used"] > 0
    assert result.metrics["lagged_logistic"]["folds_used"] > 0
