"""Tests for replay-specific chronological model comparison."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.ml.replay_models import (
    REPLAY_FEATURE_NAMES,
    chronological_replay_folds,
    train_replay_candidates,
    train_runtime_replay_candidates,
)
from hypervector.ml.feature_matrix import FEATURE_NAMES


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
    assert result.metrics["lightgbm"]["worst_fold_log_loss"] >= 0.0
    assert result.metrics["lightgbm"]["oos_samples"] > 0
    assert "auc_mean" in result.metrics["lightgbm"]
    assert "calibration_bias_mean" in result.metrics["lightgbm"]


def _runtime_rows(n_rows: int = 120, *, one_class: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    signal = np.arange(n_rows, dtype=np.int64) * 3_600_000
    frame = pd.DataFrame(
        {
            "signal_ts_ms": signal,
            "outcome_ts_ms": signal + 60_000,
            "direction": "long",
            "label": 1 if one_class else np.arange(n_rows) % 3 == 0,
        }
    )
    for name in FEATURE_NAMES:
        frame[name] = rng.normal(size=n_rows)
    return frame


def test_train_runtime_candidates_are_annotation_only_and_loadable(tmp_path: Path):
    """Runtime candidates retain the deployed feature contract without promotion."""
    result = train_runtime_replay_candidates(
        _runtime_rows(),
        tmp_path / "runtime",
        direction="long",
        n_splits=3,
        embargo_minutes=30,
    )

    assert result.status == "trained_annotation_only"
    assert result.lightgbm_path is not None and result.lightgbm_path.is_file()
    assert result.temporal_logistic_path is not None
    assert result.lagged_logistic_path is not None
    metadata = pd.read_json(result.metadata_path, typ="series")
    assert metadata["decision_policy"] == "annotation_only"
    assert metadata["installed"] is False
    assert metadata["feature_names"] == FEATURE_NAMES


def test_runtime_candidate_one_class_writes_insufficiency_report(tmp_path: Path):
    """One-class evidence is reported rather than converted into a fake model."""
    result = train_runtime_replay_candidates(
        _runtime_rows(one_class=True),
        tmp_path / "runtime",
        direction="long",
    )

    assert result.status == "insufficient_resolved_labels"
    assert result.lightgbm_path is None
    assert result.metadata_path.is_file()
