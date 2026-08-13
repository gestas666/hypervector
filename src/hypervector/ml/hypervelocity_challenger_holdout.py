"""Tamper-evident holdout scoring for frozen Hypervelocity challengers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss

from hypervector.data.oxa_storage import file_evidence
from hypervector.ml.hypervelocity_challenger import (
    CANDIDATE_NAMES,
    _feature_sets,
    _rank_metrics,
    _top_quintile_lift,
    _validate_rows,
)
from hypervector.research.hypervelocity_metalabel import (
    BASE_FEATURE_NAMES,
    BOOK_FEATURE_NAMES,
    SEQUENCE_BOOK_FEATURE_NAMES,
)


@dataclass(frozen=True)
class FrozenHoldoutResult:
    """Predictions, metrics, and verified source evidence for one holdout."""

    metrics: dict[str, dict[str, float | int | None]]
    predictions: pd.DataFrame
    evidence: dict[str, object]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} contains a non-string key")
    return value


def _read_json(path: Path, label: str) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    return _mapping(value, label)


def _model_paths(model_dir: Path) -> dict[str, Path]:
    paths = {
        name: model_dir
        / f"{name}{'.txt' if name.startswith('lightgbm') else '.joblib'}"
        for name in CANDIDATE_NAMES
        if name != "base_rate"
    }
    missing = [path for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"frozen challenger model is missing: {missing[0]}")
    return paths


def _verify_metadata(model_dir: Path, label_column: str) -> dict[str, object]:
    path = model_dir / "metadata.json"
    metadata = dict(_read_json(path, "frozen model metadata"))
    expected = {
        "installed": False,
        "decision_policy": "annotation_only",
        "label": label_column,
        "base_features": list(BASE_FEATURE_NAMES),
        "book_features": list(BOOK_FEATURE_NAMES),
        "sequence_book_features": list(SEQUENCE_BOOK_FEATURE_NAMES),
        "searched_set": list(CANDIDATE_NAMES),
    }
    mismatches = {
        key: (metadata.get(key), value)
        for key, value in expected.items()
        if metadata.get(key) != value
    }
    if mismatches:
        raise ValueError(f"frozen model metadata contract differs: {mismatches}")
    return {"file": file_evidence(path), "contract": expected}


def _verify_training_evidence(
    report_path: Path,
    dataset_path: Path,
    model_paths: Mapping[str, Path],
) -> dict[str, object]:
    report = _read_json(report_path, "frozen training report")
    if (
        report.get("ok") is not True
        or report.get("report_only") is not True
        or report.get("runtime_strategy_changed") is not False
    ):
        raise ValueError("frozen training report is not report-only evidence")
    declared_models = _mapping(report.get("model_evidence"), "model evidence")
    for name, path in model_paths.items():
        if dict(_mapping(declared_models.get(name), name)) != file_evidence(path):
            raise ValueError(f"frozen model evidence differs: {name}")
    data_evidence = _mapping(report.get("data_evidence"), "training data evidence")
    declared_dataset = dict(_mapping(data_evidence.get("dataset"), "training dataset"))
    if declared_dataset != file_evidence(dataset_path):
        raise ValueError("frozen training dataset evidence differs")
    return {
        "report": file_evidence(report_path),
        "dataset": declared_dataset,
        "models": {name: file_evidence(path) for name, path in model_paths.items()},
    }


def _predict(
    rows: pd.DataFrame,
    training_rows: pd.DataFrame,
    model_paths: Mapping[str, Path],
    label_column: str,
) -> dict[str, np.ndarray]:
    features = _feature_sets(rows)
    base_rate = float(training_rows[label_column].mean())
    output = {"base_rate": np.full(len(rows), base_rate)}
    families = {
        "logistic_base": "base",
        "logistic_book": "book",
        "temporal_logistic_book": "temporal",
        "logistic_sequence_book": "sequence",
    }
    for name, family in families.items():
        model = joblib.load(model_paths[name])
        output[name] = np.asarray(
            model.predict_proba(features[family])[:, 1], dtype=float
        )
    for name, family in (
        ("lightgbm_base", "base"),
        ("lightgbm_book", "book"),
        ("lightgbm_sequence_book", "sequence"),
    ):
        model = lgb.Booster(model_file=str(model_paths[name]))
        output[name] = np.asarray(model.predict(features[family]), dtype=float)
    return output


def _metrics(labels: np.ndarray, predicted: np.ndarray) -> dict[str, float | int]:
    clipped = np.clip(predicted, 1e-6, 1.0 - 1e-6)
    auc, average_precision = _rank_metrics(labels, clipped)
    return {
        "samples": len(labels),
        "positives": int(labels.sum()),
        "log_loss": float(log_loss(labels, clipped, labels=[0, 1])),
        "brier": float(brier_score_loss(labels, clipped)),
        "roc_auc": auc,
        "average_precision": average_precision,
        "calibration_bias": float(clipped.mean() - labels.mean()),
        "top_quintile_lift": _top_quintile_lift(labels, clipped),
    }


def _prediction_frame(
    rows: pd.DataFrame,
    predictions: Mapping[str, np.ndarray],
    label_column: str,
) -> pd.DataFrame:
    identity = ["lifecycle_id", "segment_id", "signal_ts_ms", "outcome_ts_ms"]
    base = rows.loc[:, [name for name in identity if name in rows]].copy()
    base[label_column] = rows[label_column].to_numpy()
    return pd.concat(
        [
            base.assign(candidate=name, prediction=predicted)
            for name, predicted in predictions.items()
        ],
        ignore_index=True,
    )


def score_frozen_challengers(
    rows: pd.DataFrame,
    *,
    training_report_path: Path,
    training_dataset_path: Path,
    model_dir: Path,
    label_column: str = "liquidation_risk",
) -> FrozenHoldoutResult:
    """Score an untouched population without fitting or modifying any model."""
    _validate_rows(rows, label_column)
    training_rows = pd.read_parquet(training_dataset_path)
    _validate_rows(training_rows, label_column)
    paths = _model_paths(model_dir)
    evidence = _verify_training_evidence(
        training_report_path,
        training_dataset_path,
        paths,
    )
    evidence["metadata"] = _verify_metadata(model_dir, label_column)
    predicted = _predict(rows, training_rows, paths, label_column)
    labels = rows[label_column].astype(int).to_numpy()
    metrics = {name: _metrics(labels, values) for name, values in predicted.items()}
    return FrozenHoldoutResult(
        metrics=metrics,
        predictions=_prediction_frame(rows, predicted, label_column),
        evidence=evidence,
    )
