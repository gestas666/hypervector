"""Purged walk-forward challengers for Hypervelocity liquidation risk."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from hypervector.research.hypervelocity_metalabel import (
    BASE_FEATURE_NAMES,
    BOOK_FEATURE_NAMES,
    SEQUENCE_BOOK_FEATURE_NAMES,
)

CANDIDATE_NAMES: tuple[str, ...] = (
    "base_rate",
    "logistic_base",
    "logistic_book",
    "temporal_logistic_book",
    "lightgbm_base",
    "lightgbm_book",
    "logistic_sequence_book",
    "lightgbm_sequence_book",
)


@dataclass(frozen=True)
class WalkForwardFold:
    """One expanding chronological split with outcome-aware purging."""

    fold_id: int
    train_indices: np.ndarray
    test_indices: np.ndarray


@dataclass(frozen=True)
class HypervelocityChallengerResult:
    """Research paths, predictions, and metrics for the fixed candidate set."""

    metrics: dict[str, dict[str, float | int | None]]
    fold_metrics: pd.DataFrame
    predictions: pd.DataFrame
    model_paths: dict[str, Path]
    metadata_path: Path
    label_column: str


def _validate_rows(rows: pd.DataFrame, label_column: str) -> None:
    if not label_column.strip():
        raise ValueError("Hypervelocity challenger label column must be non-empty")
    required = {
        "signal_ts_ms",
        "outcome_ts_ms",
        label_column,
        *BASE_FEATURE_NAMES,
        *BOOK_FEATURE_NAMES,
        *SEQUENCE_BOOK_FEATURE_NAMES,
    }
    missing = required.difference(rows.columns)
    if missing:
        raise ValueError(f"Hypervelocity challenger rows missing: {sorted(missing)}")
    if rows.empty or not rows["signal_ts_ms"].is_monotonic_increasing:
        raise ValueError("Hypervelocity challenger rows must be ordered and non-empty")
    labels = rows[label_column].astype(int)
    if not labels.isin((0, 1)).all() or labels.nunique() < 2:
        raise ValueError("Hypervelocity challenger requires both label classes")


def purged_walk_forward_folds(
    rows: pd.DataFrame,
    *,
    n_splits: int = 3,
    embargo_minutes: int = 60,
) -> tuple[WalkForwardFold, ...]:
    """Return expanding folds whose training labels resolved before test time."""
    if n_splits < 1 or embargo_minutes < 0:
        raise ValueError("fold count must be positive and embargo non-negative")
    if rows.empty or not rows["signal_ts_ms"].is_monotonic_increasing:
        raise ValueError("walk-forward rows must be ordered and non-empty")
    initial = max(1, len(rows) // 2)
    boundaries = np.linspace(initial, len(rows), n_splits + 1, dtype=int)
    embargo_ms = embargo_minutes * 60_000
    folds: list[WalkForwardFold] = []
    outcomes = rows["outcome_ts_ms"].to_numpy(dtype=np.int64)
    for fold_id, (start, end) in enumerate(
        zip(boundaries[:-1], boundaries[1:], strict=True)
    ):
        if end <= start:
            continue
        cutoff = int(rows.iloc[start]["signal_ts_ms"]) - embargo_ms
        train = np.flatnonzero(outcomes[:start] < cutoff)
        if len(train):
            folds.append(WalkForwardFold(fold_id, train, np.arange(start, end)))
    return tuple(folds)


def _logistic_pipeline() -> Pipeline:
    """Create the fixed regularized and fold-local linear baseline."""
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    C=0.1,
                    max_iter=1_000,
                    random_state=42,
                ),
            ),
        ]
    )


def _lightgbm_params() -> dict[str, float | int | str | bool]:
    """Return a shallow deterministic small-sample LightGBM contract."""
    return {
        "objective": "binary",
        "metric": "binary_logloss",
        "learning_rate": 0.03,
        "num_leaves": 7,
        "max_depth": 3,
        "min_data_in_leaf": 20,
        "lambda_l2": 2.0,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "seed": 42,
        "num_threads": 1,
        "deterministic": True,
        "force_col_wise": True,
        "verbose": -1,
    }


def _lagged_features(
    frame: pd.DataFrame,
    *,
    groups: pd.Series | None = None,
    lags: int = 3,
) -> pd.DataFrame:
    """Append prior signal features without using later rows or outcomes."""
    frames = [frame.add_suffix("_t0")]
    for lag in range(1, lags + 1):
        shifted = (
            frame.shift(lag)
            if groups is None
            else frame.groupby(groups, sort=False).shift(lag)
        )
        frames.append(shifted.add_suffix(f"_lag{lag}"))
    return pd.concat(frames, axis=1)


def _feature_sets(rows: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return frozen static, prior-signal-lag, and true L2 sequence families."""
    base = rows.loc[:, BASE_FEATURE_NAMES].astype(float)
    book = rows.loc[:, BASE_FEATURE_NAMES + BOOK_FEATURE_NAMES].astype(float)
    sequence = rows.loc[
        :, BASE_FEATURE_NAMES + BOOK_FEATURE_NAMES + SEQUENCE_BOOK_FEATURE_NAMES
    ].astype(float)
    return {
        "base": base,
        "book": book,
        "temporal": _lagged_features(book, groups=rows.get("segment_id")),
        "sequence": sequence,
    }


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


def _fold_predictions(
    features: dict[str, pd.DataFrame],
    labels: np.ndarray,
    fold: WalkForwardFold,
) -> dict[str, np.ndarray]:
    train, test = fold.train_indices, fold.test_indices
    train_labels = labels[train]
    base_rate = float(np.clip(train_labels.mean(), 1e-6, 1.0 - 1e-6))
    predictions = {"base_rate": np.full(len(test), base_rate)}
    for name, family in (
        ("logistic_base", "base"),
        ("logistic_book", "book"),
        ("temporal_logistic_book", "temporal"),
        ("logistic_sequence_book", "sequence"),
    ):
        model = _logistic_pipeline().fit(features[family].iloc[train], train_labels)
        predictions[name] = model.predict_proba(features[family].iloc[test])[:, 1]
    predictions["lightgbm_base"] = _lgbm_predict(
        features["base"].iloc[train], train_labels, features["base"].iloc[test]
    )
    predictions["lightgbm_book"] = _lgbm_predict(
        features["book"].iloc[train], train_labels, features["book"].iloc[test]
    )
    predictions["lightgbm_sequence_book"] = _lgbm_predict(
        features["sequence"].iloc[train],
        train_labels,
        features["sequence"].iloc[test],
    )
    return predictions


def _rank_metrics(labels: np.ndarray, predicted: np.ndarray) -> tuple[float, float]:
    if len(np.unique(labels)) < 2:
        return float("nan"), float("nan")
    return (
        float(roc_auc_score(labels, predicted)),
        float(average_precision_score(labels, predicted)),
    )


def _top_quintile_lift(labels: np.ndarray, predicted: np.ndarray) -> float:
    base = float(labels.mean())
    if base <= 0.0 or np.ptp(predicted) <= 1e-12:
        return float("nan")
    count = max(1, math.ceil(0.2 * len(labels)))
    positions = np.argsort(-predicted, kind="stable")[:count]
    return float(labels[positions].mean() / base)


def _fold_metric_row(
    candidate: str,
    fold: WalkForwardFold,
    train_labels: np.ndarray,
    test_labels: np.ndarray,
    predicted: np.ndarray,
) -> dict[str, float | int | str]:
    clipped = np.clip(predicted, 1e-6, 1.0 - 1e-6)
    auc, average_precision = _rank_metrics(test_labels, clipped)
    return {
        "candidate": candidate,
        "fold_id": fold.fold_id,
        "train_samples": len(train_labels),
        "train_positives": int(train_labels.sum()),
        "test_samples": len(test_labels),
        "test_positives": int(test_labels.sum()),
        "log_loss": float(log_loss(test_labels, clipped, labels=[0, 1])),
        "brier": float(brier_score_loss(test_labels, clipped)),
        "roc_auc": auc,
        "average_precision": average_precision,
        "calibration_bias": float(clipped.mean() - test_labels.mean()),
        "top_quintile_lift": _top_quintile_lift(test_labels, clipped),
    }


def _prediction_rows(
    rows: pd.DataFrame,
    fold: WalkForwardFold,
    candidate: str,
    predicted: np.ndarray,
    label_column: str,
) -> pd.DataFrame:
    columns = ["signal_ts_ms", "outcome_ts_ms", label_column]
    if "segment_id" in rows:
        columns.insert(0, "segment_id")
    if "lifecycle_id" in rows:
        columns.insert(0, "lifecycle_id")
    frame = rows.iloc[fold.test_indices][columns].reset_index(drop=True).copy()
    frame["fold_id"] = fold.fold_id
    frame["candidate"] = candidate
    frame["prediction"] = predicted
    return frame


def _evaluate(
    rows: pd.DataFrame,
    folds: tuple[WalkForwardFold, ...],
    label_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    features = _feature_sets(rows)
    labels = rows[label_column].astype(int).to_numpy()
    metric_rows: list[dict[str, float | int | str]] = []
    prediction_rows: list[pd.DataFrame] = []
    for fold in folds:
        train_labels = labels[fold.train_indices]
        test_labels = labels[fold.test_indices]
        if len(np.unique(train_labels)) < 2:
            raise ValueError("purged training fold does not contain both label classes")
        if len(np.unique(test_labels)) < 2:
            raise ValueError(
                "challenger requires both label classes in every test fold; "
                f"fold {fold.fold_id} is one-class"
            )
        for candidate, predicted in _fold_predictions(features, labels, fold).items():
            metric_rows.append(
                _fold_metric_row(candidate, fold, train_labels, test_labels, predicted)
            )
            prediction_rows.append(
                _prediction_rows(rows, fold, candidate, predicted, label_column)
            )
    if not metric_rows:
        raise ValueError("no purged folds were available for challenger evaluation")
    return pd.DataFrame(metric_rows), pd.concat(prediction_rows, ignore_index=True)


def _finite_mean(values: pd.Series) -> float | None:
    observed = values.dropna().astype(float)
    return float(observed.mean()) if not observed.empty else None


def _metric_summary(
    group: pd.DataFrame,
    label_column: str,
) -> dict[str, float | int | None]:
    positives = int(group["test_positives"].sum())
    result: dict[str, float | int | None] = {
        "folds_used": int(len(group)),
        "oos_samples": int(group["test_samples"].sum()),
        "oos_positives": positives,
        "log_loss_mean": float(group["log_loss"].mean()),
        "brier_mean": float(group["brier"].mean()),
        "worst_fold_log_loss": float(group["log_loss"].max()),
        "roc_auc_mean": _finite_mean(group["roc_auc"]),
        "average_precision_mean": _finite_mean(group["average_precision"]),
        "calibration_bias_mean": float(group["calibration_bias"].mean()),
        "top_quintile_lift_mean": _finite_mean(group["top_quintile_lift"]),
    }
    if label_column == "liquidation_risk":
        result["oos_liquidations"] = positives
    return result


def _summaries(
    fold_metrics: pd.DataFrame,
    label_column: str,
) -> dict[str, dict[str, float | int | None]]:
    return {
        name: _metric_summary(
            fold_metrics.loc[fold_metrics["candidate"].eq(name)],
            label_column,
        )
        for name in CANDIDATE_NAMES
    }


def _fit_full_models(
    rows: pd.DataFrame,
    destination: Path,
    label_column: str,
) -> dict[str, Path]:
    features = _feature_sets(rows)
    labels = rows[label_column].astype(int).to_numpy()
    paths: dict[str, Path] = {}
    for name, family in (
        ("logistic_base", "base"),
        ("logistic_book", "book"),
        ("temporal_logistic_book", "temporal"),
        ("logistic_sequence_book", "sequence"),
    ):
        path = destination / f"{name}.joblib"
        joblib.dump(_logistic_pipeline().fit(features[family], labels), path)
        paths[name] = path.resolve()
    for name, family in (
        ("lightgbm_base", "base"),
        ("lightgbm_book", "book"),
        ("lightgbm_sequence_book", "sequence"),
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
    n_splits: int,
    embargo_minutes: int,
    label_column: str,
) -> None:
    positives = int(rows[label_column].sum())
    metadata = {
        "label": label_column,
        "n_samples": len(rows),
        "positives": positives,
        "positive_rate": float(rows[label_column].mean()),
        "base_features": list(BASE_FEATURE_NAMES),
        "book_features": list(BOOK_FEATURE_NAMES),
        "sequence_book_features": list(SEQUENCE_BOOK_FEATURE_NAMES),
        "searched_set": list(CANDIDATE_NAMES),
        "n_splits": n_splits,
        "embargo_minutes": embargo_minutes,
        "metrics": metrics,
        "installed": False,
        "decision_policy": "annotation_only",
        "temporal_feature_semantics": {
            "temporal_logistic_book": "prior_signal_row_lags",
            "logistic_sequence_book": "causal_l2_windows_15s_60s",
            "lightgbm_sequence_book": "causal_l2_windows_15s_60s",
        },
    }
    if label_column == "liquidation_risk":
        metadata["liquidations"] = positives
    path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def train_annotation_only_challengers(
    rows: pd.DataFrame,
    out_dir: Path | str,
    *,
    n_splits: int = 3,
    embargo_minutes: int = 60,
    label_column: str = "liquidation_risk",
) -> HypervelocityChallengerResult:
    """Evaluate and fit the frozen model set without installing any candidate."""
    _validate_rows(rows, label_column)
    folds = purged_walk_forward_folds(
        rows, n_splits=n_splits, embargo_minutes=embargo_minutes
    )
    fold_metrics, predictions = _evaluate(rows, folds, label_column)
    metrics = _summaries(fold_metrics, label_column)
    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    model_paths = _fit_full_models(rows, destination, label_column)
    metadata_path = destination / "metadata.json"
    _write_metadata(
        metadata_path,
        rows,
        metrics,
        n_splits,
        embargo_minutes,
        label_column,
    )
    return HypervelocityChallengerResult(
        metrics=metrics,
        fold_metrics=fold_metrics,
        predictions=predictions,
        model_paths=model_paths,
        metadata_path=metadata_path.resolve(),
        label_column=label_column,
    )
