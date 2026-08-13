"""Purged report-only challengers for five-minute directional outcomes."""

from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from hypervector.ml.hypervelocity_challenger import (
    WalkForwardFold,
    _fold_metric_row,
    _lightgbm_params,
    _logistic_pipeline,
    _metric_summary,
    purged_walk_forward_folds,
)
from hypervector.research.low_tf_l2_dataset import FEATURE_NAMES


CANDIDATE_NAMES: tuple[str, ...] = (
    "base_rate",
    "logistic_l2",
    "lightgbm_l2",
)
RETURN_CANDIDATE_NAMES: tuple[str, ...] = (
    "ridge_return",
    "lightgbm_return",
)
_DIRECTIONAL_FEATURES = frozenset(
    {
        "return_1_bps",
        "return_3_bps",
        "return_12_bps",
        "trade_flow_imbalance",
        "imbalance_5_last",
        "imbalance_5_mean_60s",
        "imbalance_5_delta_60s",
        "imbalance_10_last",
        "micro_price_delta_bps",
    }
)


@dataclass(frozen=True)
class LowTimeframeChallengerResult:
    """Out-of-sample model probabilities and their purged fold identities."""

    metrics: dict[str, dict[str, float | int | None]]
    fold_metrics: pd.DataFrame
    predictions: pd.DataFrame
    folds: tuple[WalkForwardFold, ...]


@dataclass(frozen=True)
class LowTimeframeReturnChallengerResult:
    """Out-of-sample expected-return forecasts and purged fold identities."""

    metrics: dict[str, dict[str, float | int | None]]
    fold_metrics: pd.DataFrame
    predictions: pd.DataFrame
    folds: tuple[WalkForwardFold, ...]


def evaluate_low_tf_directional_challengers(
    rows: pd.DataFrame,
    *,
    n_splits: int = 3,
    embargo_minutes: int = 60,
) -> LowTimeframeChallengerResult:
    """Evaluate the fixed base-rate, logistic, and LightGBM candidate set."""
    _validate_rows(rows)
    folds = _grouped_folds(
        rows,
        n_splits=n_splits,
        embargo_minutes=embargo_minutes,
    )
    if len(folds) != n_splits:
        raise ValueError(f"directional challenger produced {len(folds)} folds")
    features = _directional_features(rows)
    labels = rows["target_hit"].astype(int).to_numpy()
    metrics, predictions = _evaluate(rows, features, labels, folds)
    summaries = {
        name: _metric_summary(
            metrics.loc[metrics["candidate"].eq(name)],
            "target_hit",
        )
        for name in CANDIDATE_NAMES
    }
    return LowTimeframeChallengerResult(summaries, metrics, predictions, folds)


def evaluate_low_tf_return_challengers(
    rows: pd.DataFrame,
    *,
    n_splits: int = 3,
    embargo_minutes: int = 60,
) -> LowTimeframeReturnChallengerResult:
    """Evaluate fixed Ridge and shallow LightGBM gross-return regressors."""
    _validate_return_rows(rows)
    folds = _grouped_folds(
        rows,
        n_splits=n_splits,
        embargo_minutes=embargo_minutes,
    )
    if len(folds) != n_splits:
        raise ValueError(f"return challenger produced {len(folds)} folds")
    features = _directional_features(rows)
    targets = rows["gross_return_bps"].astype(float).to_numpy()
    metrics, predictions = _evaluate_returns(rows, features, targets, folds)
    summaries = {
        name: _return_metric_summary(metrics.loc[metrics["candidate"].eq(name)])
        for name in RETURN_CANDIDATE_NAMES
    }
    return LowTimeframeReturnChallengerResult(
        summaries,
        metrics,
        predictions,
        folds,
    )


def _validate_rows(rows: pd.DataFrame) -> None:
    _validate_structure(
        rows,
        {
            "signal_ts_ms",
            "outcome_ts_ms",
            "side",
            "target_hit",
            *FEATURE_NAMES,
        },
    )
    labels = rows["target_hit"].astype(int)
    if not labels.isin((0, 1)).all() or labels.nunique() < 2:
        raise ValueError("directional challenger requires both label classes")


def _validate_return_rows(rows: pd.DataFrame) -> None:
    _validate_structure(
        rows,
        {
            "signal_ts_ms",
            "outcome_ts_ms",
            "side",
            "gross_return_bps",
            *FEATURE_NAMES,
        },
    )
    targets = rows["gross_return_bps"].astype(float).to_numpy()
    if not np.isfinite(targets).all():
        raise ValueError("directional gross returns must be finite")


def _validate_structure(rows: pd.DataFrame, required: set[str]) -> None:
    missing = sorted(required.difference(rows.columns))
    if missing:
        raise ValueError(f"directional challenger rows missing: {missing}")
    if rows.empty or not rows["signal_ts_ms"].is_monotonic_increasing:
        raise ValueError("directional challenger rows must be ordered and non-empty")
    if (rows["outcome_ts_ms"] <= rows["signal_ts_ms"]).any():
        raise ValueError("directional outcomes must follow their signal")
    _validate_side_pairs(rows)


def _validate_side_pairs(rows: pd.DataFrame) -> None:
    for signal, group in rows.groupby("signal_ts_ms", sort=False):
        sides = group["side"].tolist()
        if len(sides) != 2 or set(sides) != {"long", "short"}:
            raise ValueError(
                f"signal {signal} must contain exactly one long and short row"
            )


def _grouped_folds(
    rows: pd.DataFrame,
    *,
    n_splits: int,
    embargo_minutes: int,
) -> tuple[WalkForwardFold, ...]:
    signals = (
        rows.groupby("signal_ts_ms", sort=False, as_index=False)["outcome_ts_ms"]
        .max()
        .reset_index(drop=True)
    )
    base = purged_walk_forward_folds(
        signals,
        n_splits=n_splits,
        embargo_minutes=embargo_minutes,
    )
    output: list[WalkForwardFold] = []
    signal_values = rows["signal_ts_ms"].to_numpy(dtype=np.int64)
    for fold in base:
        train_signals = signals.iloc[fold.train_indices]["signal_ts_ms"]
        test_signals = signals.iloc[fold.test_indices]["signal_ts_ms"]
        train = np.flatnonzero(np.isin(signal_values, train_signals))
        test = np.flatnonzero(np.isin(signal_values, test_signals))
        output.append(WalkForwardFold(fold.fold_id, train, test))
    return tuple(output)


def _directional_features(rows: pd.DataFrame) -> pd.DataFrame:
    features = rows.loc[:, FEATURE_NAMES].astype(float).copy()
    sign = rows["side"].map({"long": 1.0, "short": -1.0})
    if sign.isna().any():
        raise ValueError("directional side must be long or short")
    for name in _DIRECTIONAL_FEATURES:
        features[name] = features[name] * sign.to_numpy()
    features.insert(0, "direction_sign", sign.to_numpy())
    if not np.isfinite(features.to_numpy()).all():
        raise ValueError("directional model features must be finite")
    return features


def _evaluate(
    rows: pd.DataFrame,
    features: pd.DataFrame,
    labels: np.ndarray,
    folds: tuple[WalkForwardFold, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    metric_rows: list[dict[str, float | int | str]] = []
    prediction_rows: list[pd.DataFrame] = []
    for fold in folds:
        train_labels = labels[fold.train_indices]
        test_labels = labels[fold.test_indices]
        if len(np.unique(train_labels)) < 2 or len(np.unique(test_labels)) < 2:
            raise ValueError(f"directional fold {fold.fold_id} is one-class")
        for candidate, predicted in _predictions(features, labels, fold).items():
            metric_rows.append(
                _fold_metric_row(
                    candidate,
                    fold,
                    train_labels,
                    test_labels,
                    predicted,
                )
            )
            prediction_rows.append(_prediction_frame(rows, fold, candidate, predicted))
    return pd.DataFrame(metric_rows), pd.concat(prediction_rows, ignore_index=True)


def _evaluate_returns(
    rows: pd.DataFrame,
    features: pd.DataFrame,
    targets: np.ndarray,
    folds: tuple[WalkForwardFold, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    metric_rows: list[dict[str, float | int | str]] = []
    prediction_rows: list[pd.DataFrame] = []
    for fold in folds:
        actual = targets[fold.test_indices]
        for candidate, predicted in _return_predictions(
            features, targets, fold
        ).items():
            metric_rows.append(_return_metric_row(candidate, fold, actual, predicted))
            prediction_rows.append(
                _return_prediction_frame(rows, fold, candidate, predicted)
            )
    return pd.DataFrame(metric_rows), pd.concat(prediction_rows, ignore_index=True)


def _predictions(
    features: pd.DataFrame,
    labels: np.ndarray,
    fold: WalkForwardFold,
) -> dict[str, np.ndarray]:
    train = fold.train_indices
    test = fold.test_indices
    train_labels = labels[train]
    base_rate = float(np.clip(train_labels.mean(), 1e-6, 1.0 - 1e-6))
    logistic = _logistic_pipeline().fit(features.iloc[train], train_labels)
    booster = lgb.train(
        _lightgbm_params(),
        lgb.Dataset(features.iloc[train], label=train_labels),
        num_boost_round=100,
    )
    return {
        "base_rate": np.full(len(test), base_rate),
        "logistic_l2": logistic.predict_proba(features.iloc[test])[:, 1],
        "lightgbm_l2": np.asarray(booster.predict(features.iloc[test]), dtype=float),
    }


def _return_predictions(
    features: pd.DataFrame,
    targets: np.ndarray,
    fold: WalkForwardFold,
) -> dict[str, np.ndarray]:
    train = fold.train_indices
    test = fold.test_indices
    ridge = Pipeline(
        [
            ("scale", StandardScaler()),
            ("model", Ridge(alpha=10.0)),
        ]
    ).fit(features.iloc[train], targets[train])
    params = return_lightgbm_params()
    booster = lgb.train(
        params,
        lgb.Dataset(features.iloc[train], label=targets[train]),
        num_boost_round=100,
    )
    return {
        "ridge_return": ridge.predict(features.iloc[test]),
        "lightgbm_return": np.asarray(
            booster.predict(features.iloc[test]), dtype=float
        ),
    }


def return_lightgbm_params() -> dict[str, float | int | str | bool]:
    """Return the deterministic conditional-mean LightGBM contract."""
    params = _lightgbm_params()
    params.update(
        {
            "objective": "regression",
            "metric": "l2",
            "min_data_in_leaf": 100,
        }
    )
    return params


def _prediction_frame(
    rows: pd.DataFrame,
    fold: WalkForwardFold,
    candidate: str,
    predicted: np.ndarray,
) -> pd.DataFrame:
    columns = ["signal_ts_ms", "outcome_ts_ms", "side", "target_hit"]
    frame = rows.iloc[fold.test_indices][columns].reset_index(drop=True).copy()
    frame["fold_id"] = fold.fold_id
    frame["candidate"] = candidate
    frame["prediction"] = predicted
    return frame


def _return_prediction_frame(
    rows: pd.DataFrame,
    fold: WalkForwardFold,
    candidate: str,
    predicted: np.ndarray,
) -> pd.DataFrame:
    columns = ["signal_ts_ms", "outcome_ts_ms", "side", "gross_return_bps"]
    frame = rows.iloc[fold.test_indices][columns].reset_index(drop=True).copy()
    frame["fold_id"] = fold.fold_id
    frame["candidate"] = candidate
    frame["predicted_gross_return_bps"] = predicted
    return frame


def _return_metric_row(
    candidate: str,
    fold: WalkForwardFold,
    actual: np.ndarray,
    predicted: np.ndarray,
) -> dict[str, float | int | str]:
    error = predicted - actual
    actual_rank = pd.Series(actual).rank(method="average")
    predicted_rank = pd.Series(predicted).rank(method="average")
    rank_ic = _rank_correlation(actual_rank, predicted_rank)
    return {
        "candidate": candidate,
        "fold_id": fold.fold_id,
        "train_samples": len(fold.train_indices),
        "test_samples": len(fold.test_indices),
        "mae_bps": float(np.mean(np.abs(error))),
        "rmse_bps": float(np.sqrt(np.mean(np.square(error)))),
        "rank_ic": rank_ic,
        "prediction_mean_bps": float(np.mean(predicted)),
        "actual_mean_bps": float(np.mean(actual)),
    }


def _rank_correlation(actual: pd.Series, predicted: pd.Series) -> float:
    if actual.nunique() < 2 or predicted.nunique() < 2:
        return float("nan")
    return float(actual.corr(predicted))


def _return_metric_summary(
    rows: pd.DataFrame,
) -> dict[str, float | int | None]:
    if rows.empty:
        raise ValueError("return challenger metric rows must be non-empty")
    return {
        "folds_used": len(rows),
        "oos_samples": int(rows["test_samples"].sum()),
        "mae_bps_mean": float(rows["mae_bps"].mean()),
        "rmse_bps_mean": float(rows["rmse_bps"].mean()),
        "rank_ic_mean": float(rows["rank_ic"].mean()),
        "rank_ic_worst_fold": float(rows["rank_ic"].min()),
    }
