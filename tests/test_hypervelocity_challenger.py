"""Chronological model-comparison tests for Hypervelocity liquidation risk."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hypervector.ml.hypervelocity_challenger import (
    CANDIDATE_NAMES,
    _feature_sets,
    _top_quintile_lift,
    purged_walk_forward_folds,
    train_annotation_only_challengers,
)
from hypervector.research.hypervelocity_metalabel import (
    BASE_FEATURE_NAMES,
    BOOK_FEATURE_NAMES,
    SEQUENCE_BOOK_FEATURE_NAMES,
)


def _model_rows(n_rows: int = 180) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    signal = np.arange(n_rows, dtype=np.int64) * 3_600_000
    labels = (np.arange(n_rows) % 9 == 0).astype(int)
    frame = pd.DataFrame(
        {
            "lifecycle_id": np.arange(n_rows),
            "signal_ts_ms": signal,
            "outcome_ts_ms": signal + 10 * 60_000,
            "liquidation_risk": labels,
        }
    )
    for name in BASE_FEATURE_NAMES + BOOK_FEATURE_NAMES + SEQUENCE_BOOK_FEATURE_NAMES:
        frame[name] = rng.normal(size=n_rows) + labels * 0.25
    frame.loc[::17, BOOK_FEATURE_NAMES[0]] = np.nan
    return frame


def test_purged_folds_require_training_outcomes_before_embargo() -> None:
    """A test signal cannot see labels that had not resolved before its embargo."""
    rows = _model_rows()

    folds = purged_walk_forward_folds(rows, n_splits=3, embargo_minutes=60)

    assert len(folds) == 3
    for fold in folds:
        train = rows.iloc[fold.train_indices]
        test = rows.iloc[fold.test_indices]
        assert train["outcome_ts_ms"].max() < (test["signal_ts_ms"].min() - 60 * 60_000)


def test_challengers_share_folds_and_remain_annotation_only(tmp_path: Path) -> None:
    """Every model uses identical OOS rows and writes no installed model contract."""
    result = train_annotation_only_challengers(
        _model_rows(),
        tmp_path / "candidate",
        n_splits=3,
        embargo_minutes=60,
    )

    assert tuple(result.metrics) == CANDIDATE_NAMES
    assert result.predictions["candidate"].nunique() == len(CANDIDATE_NAMES)
    sample_counts = result.predictions.groupby("candidate").size().to_dict()
    assert len(set(sample_counts.values())) == 1
    assert all(metrics["folds_used"] == 3 for metrics in result.metrics.values())
    assert all("average_precision_mean" in row for row in result.metrics.values())
    assert all("worst_fold_log_loss" in row for row in result.metrics.values())
    assert all(path.is_file() for path in result.model_paths.values())
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["installed"] is False
    assert metadata["decision_policy"] == "annotation_only"
    assert metadata["label"] == "liquidation_risk"
    assert metadata["searched_set"] == list(CANDIDATE_NAMES)
    assert metadata["temporal_feature_semantics"]["temporal_logistic_book"] == (
        "prior_signal_row_lags"
    )
    assert metadata["temporal_feature_semantics"]["logistic_sequence_book"] == (
        "causal_l2_windows_15s_60s"
    )


def test_challenger_training_rejects_one_class_evidence(tmp_path: Path) -> None:
    """A one-class replay cannot produce a success-shaped classifier."""
    rows = _model_rows()
    rows["liquidation_risk"] = 0

    with pytest.raises(ValueError, match="both label classes"):
        train_annotation_only_challengers(rows, tmp_path / "candidate")


def test_challenger_preserves_explicit_loss_label(tmp_path: Path) -> None:
    """Stop-risk training must not misrepresent every loss as liquidation."""
    rows = _model_rows().rename(columns={"liquidation_risk": "loss_risk"})

    result = train_annotation_only_challengers(
        rows,
        tmp_path / "candidate",
        label_column="loss_risk",
    )

    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["label"] == "loss_risk"
    assert metadata["positives"] == int(rows["loss_risk"].sum())
    assert "loss_risk" in result.predictions
    assert "liquidation_risk" not in result.predictions


def test_temporal_signal_lags_reset_at_segment_boundaries() -> None:
    """Disconnected replay blocks must not masquerade as adjacent observations."""
    rows = _model_rows(8)
    rows["segment_id"] = ["a"] * 4 + ["b"] * 4
    rows[BASE_FEATURE_NAMES[0]] = np.arange(8, dtype=float)

    temporal = _feature_sets(rows)["temporal"]

    lag_name = f"{BASE_FEATURE_NAMES[0]}_lag1"
    assert np.isnan(temporal.loc[0, lag_name])
    assert temporal.loc[3, lag_name] == pytest.approx(2.0)
    assert np.isnan(temporal.loc[4, lag_name])
    assert temporal.loc[5, lag_name] == pytest.approx(4.0)


def test_challenger_rejects_one_class_test_fold(tmp_path: Path) -> None:
    """Five-fold eligibility requires both outcomes in every OOS fold."""
    rows = _model_rows()
    rows["liquidation_risk"] = 0
    rows.loc[:99:5, "liquidation_risk"] = 1

    with pytest.raises(ValueError, match="both label classes in every test fold"):
        train_annotation_only_challengers(
            rows,
            tmp_path / "candidate",
            n_splits=5,
        )


def test_constant_prediction_has_no_defined_ranking_lift() -> None:
    """A base-rate predictor cannot claim lift from arbitrary stable tie order."""
    labels = np.array([0, 1, 0, 0, 1], dtype=int)
    predicted = np.full(len(labels), 0.4)

    assert np.isnan(_top_quintile_lift(labels, predicted))
