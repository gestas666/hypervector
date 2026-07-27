"""Chronological model candidates for the recorded L2 impulse replay."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from hypervector.ml.feature_matrix import FEATURE_NAMES

REPLAY_FEATURE_NAMES: tuple[str, ...] = (
    "impulse_score",
    "momentum_score",
    "velocity_bps_1s",
    "velocity_bps_3s",
    "velocity_bps_5s",
    "acceleration_bps",
    "feature_age_ms",
    "obi_5",
    "obi_10",
    "obi_25",
    "obi_ema_1s",
    "obi_ema_5s",
    "obi_persistence_s",
    "spread_bps",
    "bid_depth_10",
    "ask_depth_10",
    "aggressor_ratio_5s",
    "cancel_rate_5s",
    "direction_sign",
)


@dataclass(frozen=True)
class ReplayCandidateResult:
    """Paths and chronological metrics for all replay model candidates."""

    lightgbm_path: Path
    temporal_logistic_path: Path
    lagged_logistic_path: Path
    metadata_path: Path
    metrics: dict[str, dict[str, float | int | None]]


@dataclass(frozen=True)
class RuntimeReplayCandidateResult:
    """Outcome of runtime-compatible replay candidate training."""

    status: str
    direction: str
    n_samples: int
    positive_rate: float | None
    lightgbm_path: Path | None
    temporal_logistic_path: Path | None
    lagged_logistic_path: Path | None
    metadata_path: Path
    metrics: dict[str, dict[str, float | int | None]]


def chronological_replay_folds(
    rows: pd.DataFrame,
    *,
    n_splits: int = 4,
    embargo_minutes: int = 60,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Return expanding folds with outcomes purged before each test embargo."""
    if n_splits < 1:
        raise ValueError("n_splits must be positive")
    ordered = rows.sort_values("entry_ts_ms").reset_index(drop=True)
    initial = max(1, len(ordered) // 2)
    boundaries = np.linspace(initial, len(ordered), n_splits + 1, dtype=int)
    embargo_ms = int(embargo_minutes) * 60_000
    folds: list[tuple[np.ndarray, np.ndarray]] = []
    for start, end in zip(boundaries[:-1], boundaries[1:], strict=True):
        if end <= start:
            continue
        test = np.arange(start, end, dtype=np.int64)
        cutoff = int(ordered.iloc[start]["entry_ts_ms"]) - embargo_ms
        train = np.flatnonzero(
            ordered.iloc[:start]["exit_ts_ms"].to_numpy(dtype=np.int64) < cutoff
        )
        if len(train) and len(test):
            folds.append((train, test))
    return folds


def _feature_frame(rows: pd.DataFrame) -> pd.DataFrame:
    """Build the shared runtime-contract feature matrix."""
    frame = rows.copy()
    frame["direction_sign"] = np.where(frame["direction"] == "long", 1.0, -1.0)
    missing = set(REPLAY_FEATURE_NAMES) - set(frame.columns)
    if missing:
        raise ValueError(f"replay rows missing features: {sorted(missing)}")
    return frame[list(REPLAY_FEATURE_NAMES)].astype(float)


def _lgbm_params(y_train: np.ndarray) -> dict[str, float | int | str]:
    """Return compact class-aware parameters for the replay candidate."""
    positives = max(1, int(y_train.sum()))
    negatives = max(1, len(y_train) - positives)
    return {
        "objective": "binary",
        "metric": "binary_logloss",
        "learning_rate": 0.03,
        "num_leaves": 15,
        "min_data_in_leaf": 10,
        "lambda_l2": 1.0,
        "scale_pos_weight": float(negatives / positives),
        "verbose": -1,
        "seed": 42,
    }


def _temporal_logistic() -> Pipeline:
    """Create a regularized linear baseline over temporal replay features."""
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    C=1.0,
                    class_weight="balanced",
                    max_iter=1_000,
                    random_state=42,
                ),
            ),
        ]
    )


def _lagged_feature_frame(features: pd.DataFrame, *, lags: int = 3) -> pd.DataFrame:
    """Add prior event rows without using any feature from the future."""
    if lags < 1:
        raise ValueError("lags must be positive")
    frames = [features.add_suffix("_t0")]
    frames.extend(
        features.shift(lag).add_suffix(f"_lag{lag}") for lag in range(1, lags + 1)
    )
    return pd.concat(frames, axis=1)


def _score_predictions(
    y_test: np.ndarray,
    predictions: np.ndarray,
) -> tuple[float, float]:
    """Return binary log loss and Brier score for one fold."""
    clipped = np.clip(predictions, 1e-6, 1.0 - 1e-6)
    return (
        float(log_loss(y_test, clipped, labels=[0, 1])),
        float(brier_score_loss(y_test, clipped)),
    )


def _metric_summary(
    log_losses: list[float],
    briers: list[float],
    baselines: list[float],
    aucs: list[float],
    calibration_biases: list[float],
    sample_counts: list[int],
) -> dict[str, float | int | None]:
    """Aggregate fold metrics without applying a promotion gate."""
    return {
        "folds_used": len(log_losses),
        "log_loss_mean": float(np.mean(log_losses)),
        "brier_mean": float(np.mean(briers)),
        "baseline_log_loss_mean": float(np.mean(baselines)),
        "worst_fold_log_loss": float(np.max(log_losses)),
        "auc_mean": float(np.mean(aucs)) if aucs else None,
        "calibration_bias_mean": float(np.mean(calibration_biases)),
        "oos_samples": int(sum(sample_counts)),
    }


def _record_fold_score(
    values: dict[str, list[float] | list[int]],
    labels: np.ndarray,
    predicted: np.ndarray,
    baseline: float,
) -> None:
    """Record one candidate's proper scores and calibration diagnostics."""
    ll, br = _score_predictions(labels, predicted)
    values["log_losses"].append(ll)
    values["briers"].append(br)
    values["baselines"].append(baseline)
    values["calibration_biases"].append(float(np.mean(predicted) - np.mean(labels)))
    values["sample_counts"].append(len(labels))
    if len(np.unique(labels)) > 1:
        values["aucs"].append(float(roc_auc_score(labels, predicted)))


def _walk_forward_metrics(
    rows: pd.DataFrame,
    features: pd.DataFrame,
    labels: np.ndarray,
    *,
    n_splits: int,
    embargo_minutes: int,
) -> dict[str, dict[str, float | int | None]]:
    """Evaluate LightGBM and logistic on identical chronological folds."""
    scores = {
        name: {
            "log_losses": [],
            "briers": [],
            "baselines": [],
            "aucs": [],
            "calibration_biases": [],
            "sample_counts": [],
        }
        for name in ("lightgbm", "temporal_logistic", "lagged_logistic")
    }
    lagged = _lagged_feature_frame(features)
    for train, test in chronological_replay_folds(
        rows,
        n_splits=n_splits,
        embargo_minutes=embargo_minutes,
    ):
        if len(np.unique(labels[train])) < 2:
            continue
        booster = lgb.train(
            _lgbm_params(labels[train]),
            lgb.Dataset(features.iloc[train], label=labels[train]),
            num_boost_round=150,
        )
        logistic = _temporal_logistic().fit(features.iloc[train], labels[train])
        lagged_logistic = _temporal_logistic().fit(lagged.iloc[train], labels[train])
        predictions = {
            "lightgbm": booster.predict(features.iloc[test]),
            "temporal_logistic": logistic.predict_proba(features.iloc[test])[:, 1],
            "lagged_logistic": lagged_logistic.predict_proba(lagged.iloc[test])[:, 1],
        }
        base_p = float(np.clip(labels[train].mean(), 1e-6, 1.0 - 1e-6))
        baseline = float(
            log_loss(labels[test], np.full(len(test), base_p), labels=[0, 1])
        )
        for name, predicted in predictions.items():
            _record_fold_score(scores[name], labels[test], predicted, baseline)
    if not scores["lightgbm"]["log_losses"]:
        raise RuntimeError("no chronological replay folds contained both label classes")
    return {name: _metric_summary(**values) for name, values in scores.items()}


def _write_metadata(
    path: Path,
    *,
    n_samples: int,
    positive_rate: float,
    embargo_minutes: int,
    metrics: dict[str, dict[str, float | int | None]],
) -> None:
    """Write the candidate contract and empirical scores."""
    metadata = {
        "n_samples": n_samples,
        "positive_rate": positive_rate,
        "label": "recorded replay net_margin_pct > 0 after configured costs",
        "feature_names": list(REPLAY_FEATURE_NAMES),
        "embargo_minutes": embargo_minutes,
        "metrics": metrics,
        "installed": False,
        "decision_policy": "annotation_only",
        "candidate_models": ["lightgbm", "temporal_logistic", "lagged_logistic"],
    }
    path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_runtime_metadata(
    path: Path,
    *,
    status: str,
    direction: str,
    n_samples: int,
    positive_rate: float | None,
    embargo_minutes: int,
    metrics: dict[str, dict[str, float | int | None]],
    reason: str | None,
) -> None:
    """Write an annotation-only runtime candidate or insufficiency contract."""
    metadata = {
        "status": status,
        "reason": reason,
        "direction": direction,
        "n_samples": n_samples,
        "positive_rate": positive_rate,
        "label": "maker outcomes resolved identically under all fill challengers",
        "feature_names": list(FEATURE_NAMES),
        "embargo_minutes": embargo_minutes,
        "metrics": metrics,
        "installed": False,
        "decision_policy": "annotation_only",
        "candidate_models": ["lightgbm", "temporal_logistic", "lagged_logistic"],
    }
    path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _runtime_result(
    destination: Path,
    *,
    status: str,
    direction: str,
    rows: pd.DataFrame,
    embargo_minutes: int,
    metrics: dict[str, dict[str, float | int | None]],
    reason: str | None,
) -> RuntimeReplayCandidateResult:
    """Persist and return a runtime training assessment."""
    metadata_path = destination / "metalabel_metadata.json"
    positive_rate = None if rows.empty else float(rows["label"].mean())
    _write_runtime_metadata(
        metadata_path,
        status=status,
        direction=direction,
        n_samples=len(rows),
        positive_rate=positive_rate,
        embargo_minutes=embargo_minutes,
        metrics=metrics,
        reason=reason,
    )
    trained = status == "trained_annotation_only"
    return RuntimeReplayCandidateResult(
        status=status,
        direction=direction,
        n_samples=len(rows),
        positive_rate=positive_rate,
        lightgbm_path=(destination / "metalabel_lgbm.txt").resolve()
        if trained
        else None,
        temporal_logistic_path=(destination / "temporal_logistic.joblib").resolve()
        if trained
        else None,
        lagged_logistic_path=(destination / "lagged_logistic.joblib").resolve()
        if trained
        else None,
        metadata_path=metadata_path.resolve(),
        metrics=metrics,
    )


def _prepare_runtime_rows(
    rows: pd.DataFrame, direction: str
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, np.ndarray]:
    """Validate and order one direction's runtime replay evidence."""
    required = {"signal_ts_ms", "outcome_ts_ms", "direction", "label", *FEATURE_NAMES}
    missing = required.difference(rows.columns)
    if missing:
        raise ValueError(f"runtime replay rows missing fields: {sorted(missing)}")
    ordered = (
        rows.loc[rows["direction"] == direction]
        .sort_values("signal_ts_ms")
        .reset_index(drop=True)
    )
    chronology = ordered.rename(
        columns={"signal_ts_ms": "entry_ts_ms", "outcome_ts_ms": "exit_ts_ms"}
    )
    return (
        ordered,
        chronology,
        ordered[FEATURE_NAMES].astype(float),
        ordered["label"].astype(int).to_numpy(),
    )


def _fit_runtime_models(
    destination: Path, features: pd.DataFrame, labels: np.ndarray
) -> None:
    """Fit and save the three annotation-only runtime challengers."""
    booster = lgb.train(
        _lgbm_params(labels), lgb.Dataset(features, label=labels), num_boost_round=150
    )
    booster.save_model(str(destination / "metalabel_lgbm.txt"))
    joblib.dump(
        _temporal_logistic().fit(features, labels),
        destination / "temporal_logistic.joblib",
    )
    joblib.dump(
        _temporal_logistic().fit(_lagged_feature_frame(features), labels),
        destination / "lagged_logistic.joblib",
    )


def train_runtime_replay_candidates(
    rows: pd.DataFrame,
    out_dir: Path | str,
    *,
    direction: str,
    n_splits: int = 4,
    embargo_minutes: int = 60,
) -> RuntimeReplayCandidateResult:
    """Train runtime-schema replay challengers, or persist why training is undefined."""
    ordered, chronology, features, labels = _prepare_runtime_rows(rows, direction)
    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    if ordered.empty or len(np.unique(labels)) < 2:
        return _runtime_result(
            destination,
            status="insufficient_resolved_labels",
            direction=direction,
            rows=ordered,
            embargo_minutes=embargo_minutes,
            metrics={},
            reason="resolved labels do not contain both outcome classes",
        )
    try:
        metrics = _walk_forward_metrics(
            chronology,
            features,
            labels,
            n_splits=n_splits,
            embargo_minutes=embargo_minutes,
        )
    except RuntimeError as exc:
        return _runtime_result(
            destination,
            status="insufficient_resolved_labels",
            direction=direction,
            rows=ordered,
            embargo_minutes=embargo_minutes,
            metrics={},
            reason=str(exc),
        )
    _fit_runtime_models(destination, features, labels)
    return _runtime_result(
        destination,
        status="trained_annotation_only",
        direction=direction,
        rows=ordered,
        embargo_minutes=embargo_minutes,
        metrics=metrics,
        reason=None,
    )


def train_replay_candidates(
    rows: pd.DataFrame,
    out_dir: Path | str,
    *,
    n_splits: int = 4,
    embargo_minutes: int = 60,
) -> ReplayCandidateResult:
    """Train LightGBM and temporal-logistic candidates on replay outcomes."""
    ordered = rows.sort_values("entry_ts_ms").reset_index(drop=True)
    features = _feature_frame(ordered)
    labels = (ordered["net_margin_pct"].astype(float) > 0.0).astype(int).to_numpy()
    if len(np.unique(labels)) < 2:
        raise RuntimeError("replay candidate training requires both outcome classes")
    metrics = _walk_forward_metrics(
        ordered,
        features,
        labels,
        n_splits=n_splits,
        embargo_minutes=embargo_minutes,
    )
    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    booster = lgb.train(
        _lgbm_params(labels),
        lgb.Dataset(features, label=labels),
        num_boost_round=150,
    )
    lightgbm_path = destination / "replay_lightgbm.txt"
    booster.save_model(str(lightgbm_path))
    logistic = _temporal_logistic().fit(features, labels)
    logistic_path = destination / "replay_temporal_logistic.joblib"
    joblib.dump(logistic, logistic_path)
    lagged_logistic = _temporal_logistic().fit(_lagged_feature_frame(features), labels)
    lagged_logistic_path = destination / "replay_lagged_logistic.joblib"
    joblib.dump(lagged_logistic, lagged_logistic_path)
    metadata_path = destination / "replay_model_metadata.json"
    _write_metadata(
        metadata_path,
        n_samples=len(ordered),
        positive_rate=float(labels.mean()),
        embargo_minutes=embargo_minutes,
        metrics=metrics,
    )
    return ReplayCandidateResult(
        lightgbm_path=lightgbm_path.resolve(),
        temporal_logistic_path=logistic_path.resolve(),
        lagged_logistic_path=lagged_logistic_path.resolve(),
        metadata_path=metadata_path.resolve(),
        metrics=metrics,
    )
