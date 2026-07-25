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
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

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
    """Paths and chronological metrics for both replay model candidates."""

    lightgbm_path: Path
    temporal_logistic_path: Path
    metadata_path: Path
    metrics: dict[str, dict[str, float | int]]


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
) -> dict[str, float | int]:
    """Aggregate fold metrics without applying a promotion gate."""
    return {
        "folds_used": len(log_losses),
        "log_loss_mean": float(np.mean(log_losses)),
        "brier_mean": float(np.mean(briers)),
        "baseline_log_loss_mean": float(np.mean(baselines)),
    }


def _walk_forward_metrics(
    rows: pd.DataFrame,
    features: pd.DataFrame,
    labels: np.ndarray,
    *,
    n_splits: int,
    embargo_minutes: int,
) -> dict[str, dict[str, float | int]]:
    """Evaluate LightGBM and logistic on identical chronological folds."""
    scores = {
        name: {"ll": [], "br": [], "base": []}
        for name in ("lightgbm", "temporal_logistic")
    }
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
        predictions = {
            "lightgbm": booster.predict(features.iloc[test]),
            "temporal_logistic": logistic.predict_proba(features.iloc[test])[:, 1],
        }
        base_p = float(np.clip(labels[train].mean(), 1e-6, 1.0 - 1e-6))
        baseline = float(
            log_loss(labels[test], np.full(len(test), base_p), labels=[0, 1])
        )
        for name, predicted in predictions.items():
            ll, br = _score_predictions(labels[test], predicted)
            scores[name]["ll"].append(ll)
            scores[name]["br"].append(br)
            scores[name]["base"].append(baseline)
    if not scores["lightgbm"]["ll"]:
        raise RuntimeError("no chronological replay folds contained both label classes")
    return {
        name: _metric_summary(values["ll"], values["br"], values["base"])
        for name, values in scores.items()
    }


def _write_metadata(
    path: Path,
    *,
    n_samples: int,
    positive_rate: float,
    embargo_minutes: int,
    metrics: dict[str, dict[str, float | int]],
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
    }
    path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
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
        metadata_path=metadata_path.resolve(),
        metrics=metrics,
    )
