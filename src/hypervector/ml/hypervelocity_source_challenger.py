"""Purged source-state challengers for Hypervelocity liquidation risk."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from hypervector.ml.hypervelocity_challenger import (
    _fold_metric_row,
    _lightgbm_params,
    _logistic_pipeline,
    _metric_summary,
    _prediction_rows,
    purged_walk_forward_folds,
)
from hypervector.research.hypervelocity_metalabel import (
    BASE_FEATURE_NAMES,
    BOOK_FEATURE_NAMES,
    SEQUENCE_BOOK_FEATURE_NAMES,
)
from hypervector.research.hypervelocity_source_features import SOURCE_FEATURE_NAMES

SOURCE_CANDIDATE_NAMES: tuple[str, ...] = (
    "base_rate",
    "logistic_source_state",
    "lightgbm_base",
    "lightgbm_source_state",
    "lightgbm_source_sequence",
)


@dataclass(frozen=True)
class SourceChallengerResult:
    """Persisted development models and their purged OOS diagnostics."""

    metrics: dict[str, dict[str, float | int | None]]
    fold_metrics: pd.DataFrame
    predictions: pd.DataFrame
    model_paths: dict[str, Path]
    metadata_path: Path


def _validate_rows(rows: pd.DataFrame, label_column: str) -> None:
    required = {
        "signal_ts_ms",
        "outcome_ts_ms",
        label_column,
        *BASE_FEATURE_NAMES,
        *BOOK_FEATURE_NAMES,
        *SEQUENCE_BOOK_FEATURE_NAMES,
        *SOURCE_FEATURE_NAMES,
    }
    missing = required.difference(rows.columns)
    if missing:
        raise ValueError(f"source challenger rows missing: {sorted(missing)}")
    if rows.empty or not rows["signal_ts_ms"].is_monotonic_increasing:
        raise ValueError("source challenger rows must be ordered and non-empty")
    labels = rows[label_column].astype(int)
    if not labels.isin((0, 1)).all() or labels.nunique() < 2:
        raise ValueError("source challenger requires both label classes")


def _feature_sets(rows: pd.DataFrame) -> dict[str, pd.DataFrame]:
    base = rows.loc[:, BASE_FEATURE_NAMES].astype(float)
    source = rows.loc[:, BASE_FEATURE_NAMES + SOURCE_FEATURE_NAMES].astype(float)
    sequence = rows.loc[
        :,
        BASE_FEATURE_NAMES
        + BOOK_FEATURE_NAMES
        + SEQUENCE_BOOK_FEATURE_NAMES
        + SOURCE_FEATURE_NAMES,
    ].astype(float)
    return {"base": base, "source": source, "source_sequence": sequence}


def _lgbm_predict(
    train: pd.DataFrame,
    labels: np.ndarray,
    test: pd.DataFrame,
) -> np.ndarray:
    booster = lgb.train(
        _lightgbm_params(),
        lgb.Dataset(train, label=labels),
        num_boost_round=100,
    )
    return np.asarray(booster.predict(test), dtype=float)


def _predictions(
    features: dict[str, pd.DataFrame],
    labels: np.ndarray,
    train: np.ndarray,
    test: np.ndarray,
) -> dict[str, np.ndarray]:
    train_labels = labels[train]
    base_rate = float(np.clip(train_labels.mean(), 1e-6, 1.0 - 1e-6))
    output = {"base_rate": np.full(len(test), base_rate)}
    logistic = _logistic_pipeline().fit(features["source"].iloc[train], train_labels)
    output["logistic_source_state"] = logistic.predict_proba(
        features["source"].iloc[test]
    )[:, 1]
    for name, family in (
        ("lightgbm_base", "base"),
        ("lightgbm_source_state", "source"),
        ("lightgbm_source_sequence", "source_sequence"),
    ):
        output[name] = _lgbm_predict(
            features[family].iloc[train],
            train_labels,
            features[family].iloc[test],
        )
    return output


def _evaluate(
    rows: pd.DataFrame,
    *,
    n_splits: int,
    embargo_minutes: int,
    label_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    folds = purged_walk_forward_folds(
        rows,
        n_splits=n_splits,
        embargo_minutes=embargo_minutes,
    )
    if len(folds) != n_splits:
        raise ValueError(f"source challenger produced {len(folds)} of {n_splits} folds")
    features = _feature_sets(rows)
    labels = rows[label_column].astype(int).to_numpy()
    metrics: list[dict[str, float | int | str]] = []
    predictions: list[pd.DataFrame] = []
    for fold in folds:
        train_labels = labels[fold.train_indices]
        test_labels = labels[fold.test_indices]
        if len(np.unique(train_labels)) < 2 or len(np.unique(test_labels)) < 2:
            raise ValueError(f"source challenger fold {fold.fold_id} is one-class")
        values = _predictions(
            features,
            labels,
            fold.train_indices,
            fold.test_indices,
        )
        for name, predicted in values.items():
            metrics.append(
                _fold_metric_row(name, fold, train_labels, test_labels, predicted)
            )
            predictions.append(
                _prediction_rows(rows, fold, name, predicted, label_column)
            )
    return pd.DataFrame(metrics), pd.concat(predictions, ignore_index=True)


def _fit_models(
    rows: pd.DataFrame,
    destination: Path,
    label_column: str,
) -> dict[str, Path]:
    features = _feature_sets(rows)
    labels = rows[label_column].astype(int).to_numpy()
    paths: dict[str, Path] = {}
    logistic_path = destination / "logistic_source_state.joblib"
    joblib.dump(_logistic_pipeline().fit(features["source"], labels), logistic_path)
    paths["logistic_source_state"] = logistic_path.resolve()
    for name, family in (
        ("lightgbm_base", "base"),
        ("lightgbm_source_state", "source"),
        ("lightgbm_source_sequence", "source_sequence"),
    ):
        booster = lgb.train(
            _lightgbm_params(),
            lgb.Dataset(features[family], label=labels),
            num_boost_round=100,
        )
        path = destination / f"{name}.txt"
        booster.save_model(str(path))
        paths[name] = path.resolve()
    return paths


def _write_metadata(
    path: Path,
    rows: pd.DataFrame,
    metrics: dict[str, dict[str, float | int | None]],
    *,
    n_splits: int,
    embargo_minutes: int,
    label_column: str,
) -> None:
    payload = {
        "label": label_column,
        "n_samples": len(rows),
        "positives": int(rows[label_column].sum()),
        "base_features": list(BASE_FEATURE_NAMES),
        "book_features": list(BOOK_FEATURE_NAMES),
        "sequence_book_features": list(SEQUENCE_BOOK_FEATURE_NAMES),
        "source_features": list(SOURCE_FEATURE_NAMES),
        "searched_set": list(SOURCE_CANDIDATE_NAMES),
        "n_splits": n_splits,
        "embargo_minutes": embargo_minutes,
        "metrics": metrics,
        "installed": False,
        "decision_policy": "annotation_only",
        "development_end_utc": "2026-01-09T00:00:00+00:00",
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def train_source_state_challengers(
    rows: pd.DataFrame,
    out_dir: Path,
    *,
    n_splits: int = 5,
    embargo_minutes: int = 60,
    label_column: str = "liquidation_risk",
) -> SourceChallengerResult:
    """Train the frozen report-only source-state development candidate set."""
    _validate_rows(rows, label_column)
    fold_metrics, predictions = _evaluate(
        rows,
        n_splits=n_splits,
        embargo_minutes=embargo_minutes,
        label_column=label_column,
    )
    metrics = {
        name: _metric_summary(
            fold_metrics.loc[fold_metrics["candidate"].eq(name)],
            label_column,
        )
        for name in SOURCE_CANDIDATE_NAMES
    }
    out_dir.mkdir(parents=True, exist_ok=False)
    paths = _fit_models(rows, out_dir, label_column)
    metadata = out_dir / "metadata.json"
    _write_metadata(
        metadata,
        rows,
        metrics,
        n_splits=n_splits,
        embargo_minutes=embargo_minutes,
        label_column=label_column,
    )
    return SourceChallengerResult(
        metrics=metrics,
        fold_metrics=fold_metrics,
        predictions=predictions,
        model_paths=paths,
        metadata_path=metadata.resolve(),
    )
