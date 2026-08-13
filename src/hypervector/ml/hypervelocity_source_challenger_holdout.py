"""Tamper-evident holdout scoring for frozen source-state challengers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from hypervector.data.oxa_storage import file_evidence
from hypervector.ml.hypervelocity_challenger_holdout import (
    FrozenHoldoutResult,
    _mapping,
    _metrics,
    _prediction_frame,
    _read_json,
)
from hypervector.ml.hypervelocity_source_challenger import (
    SOURCE_CANDIDATE_NAMES,
    _feature_sets,
    _validate_rows,
)
from hypervector.research.hypervelocity_metalabel import (
    BASE_FEATURE_NAMES,
    BOOK_FEATURE_NAMES,
    SEQUENCE_BOOK_FEATURE_NAMES,
)
from hypervector.research.hypervelocity_source_features import SOURCE_FEATURE_NAMES

_DEVELOPMENT_END_UTC = "2026-01-09T00:00:00+00:00"
_SOURCE_CANDIDATES = (
    "logistic_source_state",
    "lightgbm_source_state",
    "lightgbm_source_sequence",
)


def _model_paths(model_dir: Path) -> dict[str, Path]:
    paths = {
        name: model_dir
        / f"{name}{'.txt' if name.startswith('lightgbm') else '.joblib'}"
        for name in SOURCE_CANDIDATE_NAMES
        if name != "base_rate"
    }
    missing = [path for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"frozen source model is missing: {missing[0]}")
    return paths


def _verify_metadata(model_dir: Path, label_column: str) -> dict[str, object]:
    path = model_dir / "metadata.json"
    metadata = dict(_read_json(path, "frozen source model metadata"))
    expected = {
        "installed": False,
        "decision_policy": "annotation_only",
        "label": label_column,
        "base_features": list(BASE_FEATURE_NAMES),
        "book_features": list(BOOK_FEATURE_NAMES),
        "sequence_book_features": list(SEQUENCE_BOOK_FEATURE_NAMES),
        "source_features": list(SOURCE_FEATURE_NAMES),
        "searched_set": list(SOURCE_CANDIDATE_NAMES),
        "development_end_utc": _DEVELOPMENT_END_UTC,
    }
    mismatches = {
        key: (metadata.get(key), value)
        for key, value in expected.items()
        if metadata.get(key) != value
    }
    if mismatches:
        raise ValueError(f"frozen source metadata contract differs: {mismatches}")
    return {"file": file_evidence(path), "contract": expected}


def _verify_training_evidence(
    report_path: Path,
    dataset_path: Path,
    model_paths: Mapping[str, Path],
    metadata_path: Path,
) -> dict[str, object]:
    report = _read_json(report_path, "frozen source training report")
    required = {
        "ok": True,
        "report_only": True,
        "runtime_strategy_changed": False,
        "forward_holdout_start_utc": _DEVELOPMENT_END_UTC,
    }
    mismatches = {
        key: (report.get(key), value)
        for key, value in required.items()
        if report.get(key) != value
    }
    if mismatches:
        raise ValueError(f"frozen source training report differs: {mismatches}")
    declared_models = _mapping(report.get("model_evidence"), "model evidence")
    for name, path in model_paths.items():
        if dict(_mapping(declared_models.get(name), name)) != file_evidence(path):
            raise ValueError(f"frozen source model evidence differs: {name}")
    declared_metadata = dict(
        _mapping(declared_models.get("metadata"), "source metadata evidence")
    )
    if declared_metadata != file_evidence(metadata_path):
        raise ValueError("frozen source metadata evidence differs")
    data_evidence = _mapping(report.get("data_evidence"), "training data evidence")
    declared_dataset = dict(_mapping(data_evidence.get("dataset"), "training dataset"))
    if declared_dataset != file_evidence(dataset_path):
        raise ValueError("frozen source training dataset evidence differs")
    return {
        "report": file_evidence(report_path),
        "dataset": declared_dataset,
        "models": {name: file_evidence(path) for name, path in model_paths.items()},
        "metadata": declared_metadata,
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
    logistic = joblib.load(model_paths["logistic_source_state"])
    output["logistic_source_state"] = np.asarray(
        logistic.predict_proba(features["source"])[:, 1], dtype=float
    )
    for name, family in (
        ("lightgbm_base", "base"),
        ("lightgbm_source_state", "source"),
        ("lightgbm_source_sequence", "source_sequence"),
    ):
        model = lgb.Booster(model_file=str(model_paths[name]))
        output[name] = np.asarray(model.predict(features[family]), dtype=float)
    return output


def _metric_value(
    metrics: Mapping[str, Mapping[str, float | int | None]],
    candidate: str,
    metric: str,
) -> float:
    candidate_metrics = metrics.get(candidate)
    if candidate_metrics is None:
        raise ValueError(f"holdout metrics missing candidate: {candidate}")
    value = candidate_metrics.get(metric)
    if value is None:
        raise ValueError(f"holdout metric unavailable: {candidate}.{metric}")
    return float(value)


def source_candidate_acceptance(
    metrics: Mapping[str, Mapping[str, float | int | None]],
) -> dict[str, dict[str, bool]]:
    """Evaluate the frozen source-model statistical acceptance thresholds."""
    base_loss = _metric_value(metrics, "base_rate", "log_loss")
    bar_loss = _metric_value(metrics, "lightgbm_base", "log_loss")
    output: dict[str, dict[str, bool]] = {}
    for candidate in _SOURCE_CANDIDATES:
        loss = _metric_value(metrics, candidate, "log_loss")
        auc = _metric_value(metrics, candidate, "roc_auc")
        lift = _metric_value(metrics, candidate, "top_quintile_lift")
        checks = {
            "beats_base_rate_log_loss": loss < base_loss,
            "beats_bar_lightgbm_log_loss": loss < bar_loss,
            "roc_auc_above_0_60": auc > 0.60,
            "top_quintile_lift_above_1_50": lift > 1.50,
        }
        output[candidate] = {**checks, "passed": all(checks.values())}
    return output


def score_frozen_source_challengers(
    rows: pd.DataFrame,
    *,
    training_report_path: Path,
    training_dataset_path: Path,
    model_dir: Path,
    label_column: str = "liquidation_risk",
) -> FrozenHoldoutResult:
    """Score exact persisted source-state models without fitting or mutation."""
    _validate_rows(rows, label_column)
    training_rows = pd.read_parquet(training_dataset_path)
    _validate_rows(training_rows, label_column)
    paths = _model_paths(model_dir)
    metadata_path = model_dir / "metadata.json"
    metadata_contract = _verify_metadata(model_dir, label_column)
    evidence = _verify_training_evidence(
        training_report_path,
        training_dataset_path,
        paths,
        metadata_path,
    )
    evidence["metadata_contract"] = metadata_contract
    predicted = _predict(rows, training_rows, paths, label_column)
    labels = rows[label_column].astype(int).to_numpy()
    metrics = {name: _metrics(labels, values) for name, values in predicted.items()}
    return FrozenHoldoutResult(
        metrics=metrics,
        predictions=_prediction_frame(rows, predicted, label_column),
        evidence=evidence,
    )
