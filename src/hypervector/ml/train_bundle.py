"""Train LightGBM metalabel bundle (+ optional isotonic calibrator)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hypervector.ml.feature_matrix import FEATURE_NAMES
from hypervector.ml.purged_cv import purged_kfold_split

_MODEL_NAME = "metalabel_lgbm.txt"
_CALIBRATOR_NAME = "metalabel_calibrator.joblib"
_METADATA_NAME = "metalabel_metadata.json"

DEFAULT_LGBM_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "metric": "binary_logloss",
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_data_in_leaf": 20,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.85,
    "bagging_freq": 5,
    "lambda_l2": 1.0,
    "verbose": -1,
    "seed": 42,
}


@dataclass
class TrainResult:
    out_dir: Path
    n_samples: int
    class_balance: float
    cv: dict[str, Any]
    feature_importance_gain: dict[str, float]
    model_path: Path
    calibrator_path: Path | None
    metadata_path: Path


def _require_ml() -> tuple[Any, Any, Any]:
    try:
        import lightgbm as lgb
        import joblib
        from sklearn.isotonic import IsotonicRegression
    except ImportError as exc:
        raise ImportError(
            "metalabel training requires lightgbm, joblib, scikit-learn "
            "(uv sync --extra ml)"
        ) from exc
    return lgb, joblib, IsotonicRegression


def train_metalabel_bundle(
    labels: pd.DataFrame,
    out_dir: Path | str,
    *,
    n_splits: int = 5,
    embargo_minutes: int = 60,
    params: dict[str, Any] | None = None,
    num_boost_round: int = 200,
    extra_meta: dict[str, Any] | None = None,
) -> TrainResult:
    """Fit LGBM on labeled samples; write metalabel_lgbm.txt + calibrator + metadata."""
    lgb, joblib, IsotonicRegression = _require_ml()
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if labels.empty:
        raise ValueError("labels DataFrame is empty")
    missing = [c for c in FEATURE_NAMES if c not in labels.columns]
    if missing:
        raise ValueError(f"labels missing feature columns: {missing}")
    if "label" not in labels.columns:
        raise ValueError("labels missing 'label' column")

    df = labels.sort_values("entry_ts_ms").reset_index(drop=True)
    X = df[FEATURE_NAMES].astype(float)
    y = df["label"].astype(int).to_numpy()
    entry_ts = df["entry_ts_ms"].astype(np.int64).to_numpy()
    outcome_ts = df["outcome_ts_ms"].astype(np.int64).to_numpy()
    p = dict(DEFAULT_LGBM_PARAMS)
    if params:
        p.update(params)

    log_losses: list[float] = []
    briers: list[float] = []
    aucs: list[float] = []
    oof = np.full(len(y), np.nan)

    for fold_idx, (tr, te) in enumerate(
        purged_kfold_split(entry_ts, outcome_ts, n_splits, embargo_minutes)
    ):
        if len(np.unique(y[tr])) < 2:
            continue
        dtr = lgb.Dataset(X.iloc[tr], label=y[tr])
        dval = lgb.Dataset(X.iloc[te], label=y[te], reference=dtr)
        booster = lgb.train(
            p,
            dtr,
            num_boost_round=400,
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(30), lgb.log_evaluation(0)],
        )
        preds = np.clip(
            booster.predict(X.iloc[te], num_iteration=booster.best_iteration),
            1e-6,
            1 - 1e-6,
        )
        oof[te] = preds
        log_losses.append(float(log_loss(y[te], preds, labels=[0, 1])))
        briers.append(float(brier_score_loss(y[te], preds)))
        try:
            aucs.append(float(roc_auc_score(y[te], preds)))
        except ValueError:
            pass

    # Final fit on full data
    dall = lgb.Dataset(X, label=y)
    final = lgb.train(p, dall, num_boost_round=int(num_boost_round))
    model_path = out / _MODEL_NAME
    final.save_model(str(model_path))

    calibrator_path: Path | None = None
    valid = ~np.isnan(oof)
    if int(valid.sum()) > 50 and len(np.unique(y[valid])) > 1:
        cal = IsotonicRegression(out_of_bounds="clip")
        cal.fit(oof[valid], y[valid])
        calibrator_path = out / _CALIBRATOR_NAME
        joblib.dump(cal, calibrator_path)

    importance = dict(
        zip(
            FEATURE_NAMES,
            final.feature_importance(importance_type="gain").tolist(),
        )
    )
    baseline_ll = float(log_loss(y, np.full(len(y), y.mean()), labels=[0, 1]))
    cv = {
        "n_splits": n_splits,
        "embargo_minutes": embargo_minutes,
        "lgbm_log_loss_mean": float(np.mean(log_losses)) if log_losses else None,
        "lgbm_log_loss_std": float(np.std(log_losses)) if log_losses else None,
        "lgbm_brier_mean": float(np.mean(briers)) if briers else None,
        "lgbm_auc_mean": float(np.nanmean(aucs)) if aucs else None,
        "baseline_log_loss": baseline_ll,
        "n_cv_folds_used": len(log_losses),
    }
    meta: dict[str, Any] = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": int(len(y)),
        "n_features": len(FEATURE_NAMES),
        "class_balance": float(y.mean()),
        "feature_names": list(FEATURE_NAMES),
        "params": p,
        "cv": cv,
        "feature_importance_gain": importance,
    }
    if extra_meta:
        meta["source"] = extra_meta

    meta_path = out / _METADATA_NAME
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return TrainResult(
        out_dir=out.resolve(),
        n_samples=int(len(y)),
        class_balance=float(y.mean()),
        cv=cv,
        feature_importance_gain=importance,
        model_path=model_path.resolve(),
        calibrator_path=calibrator_path.resolve() if calibrator_path else None,
        metadata_path=meta_path.resolve(),
    )
