"""Purged Ridge and LightGBM annotations for fixed 1m impulse events."""

from __future__ import annotations

from dataclasses import dataclass
import math

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from hypervector.ml.hypervelocity_challenger import (
    WalkForwardFold,
    purged_walk_forward_folds,
)
from hypervector.ml.low_tf_directional_challenger import return_lightgbm_params
from hypervector.research.orderflow_impulse_events import MODEL_FEATURE_NAMES


CANDIDATE_NAMES: tuple[str, ...] = (
    "ridge_net_return",
    "lightgbm_net_return",
)
_SIGNED_FEATURES = frozenset(
    {
        "body_return_bps",
        "trade_flow_imbalance",
        "imbalance_5_last",
        "imbalance_5_delta",
        "micro_price_delta_bps",
    }
)


@dataclass(frozen=True)
class OrderFlowImpulseModelResult:
    """Out-of-sample annotations, fold metrics, and serialized selections."""

    metrics: dict[str, dict[str, float | int | None]]
    fold_metrics: pd.DataFrame
    predictions: pd.DataFrame
    selected: pd.DataFrame
    folds: tuple[WalkForwardFold, ...]


def evaluate_orderflow_impulse_models(
    outcomes: pd.DataFrame,
    *,
    n_splits: int = 3,
    embargo_minutes: int = 15,
) -> OrderFlowImpulseModelResult:
    """Evaluate fixed annotation regressors with outcome-time purging."""
    rows = _model_rows(outcomes)
    features = _directional_features(rows)
    folds = _grouped_folds(rows, n_splits, embargo_minutes)
    fold_metrics, predictions = _evaluate(rows, features, folds)
    selected = _select_and_serialize(predictions)
    metrics = {
        candidate: _candidate_summary(candidate, fold_metrics, selected)
        for candidate in CANDIDATE_NAMES
    }
    return OrderFlowImpulseModelResult(
        metrics, fold_metrics, predictions, selected, folds
    )


def _model_rows(outcomes: pd.DataFrame) -> pd.DataFrame:
    required = {
        "event_id",
        "symbol",
        "arm",
        "side",
        "available_at_utc",
        "entry_time_utc",
        "outcome_time_utc",
        "status",
        "net_return_bps_nominal",
        *MODEL_FEATURE_NAMES,
    }
    missing = sorted(required.difference(outcomes.columns))
    if missing:
        raise ValueError(f"order-flow model rows missing columns: {missing}")
    rows = outcomes.loc[
        outcomes["arm"].isin(("continuation_all", "reversion_all"))
        & outcomes["status"].ne("truncated")
    ].copy()
    rows = rows.sort_values(["available_at_utc", "side"]).reset_index(drop=True)
    if rows.empty:
        raise ValueError("order-flow model rows must be non-empty")
    for event_id, group in rows.groupby("event_id", sort=False):
        sides = group["side"].astype(str).tolist()
        if len(sides) != 2 or set(sides) != {"long", "short"}:
            raise ValueError(
                f"event {event_id} must contain exactly one long and short row"
            )
    return rows


def _directional_features(rows: pd.DataFrame) -> pd.DataFrame:
    features = rows.loc[:, MODEL_FEATURE_NAMES].astype(float).copy()
    sign = rows["side"].map({"long": 1.0, "short": -1.0})
    for name in _SIGNED_FEATURES:
        features[name] = features[name] * sign.to_numpy()
    features.insert(0, "symbol_sol", rows["symbol"].eq("SOL").astype(float))
    features.insert(0, "direction_sign", sign.to_numpy())
    if np.isinf(features.to_numpy()).any():
        raise ValueError("order-flow model features cannot contain infinity")
    if features.isna().all(axis=0).any():
        raise ValueError("order-flow model feature cannot be entirely missing")
    return features


def _grouped_folds(
    rows: pd.DataFrame, n_splits: int, embargo_minutes: int
) -> tuple[WalkForwardFold, ...]:
    events = rows.groupby("event_id", sort=False, as_index=False).agg(
        signal_ts_ms=("available_at_utc", _timestamp_ms),
        outcome_ts_ms=("outcome_time_utc", _maximum_timestamp_ms),
    )
    base = purged_walk_forward_folds(
        events, n_splits=n_splits, embargo_minutes=embargo_minutes
    )
    if len(base) != n_splits:
        raise ValueError(f"order-flow models produced {len(base)} folds")
    event_ids = rows["event_id"].to_numpy()
    folds: list[WalkForwardFold] = []
    for fold in base:
        train_ids = events.iloc[fold.train_indices]["event_id"]
        test_ids = events.iloc[fold.test_indices]["event_id"]
        train = np.flatnonzero(np.isin(event_ids, train_ids))
        test = np.flatnonzero(np.isin(event_ids, test_ids))
        folds.append(WalkForwardFold(fold.fold_id, train, test))
    return tuple(folds)


def _evaluate(
    rows: pd.DataFrame,
    features: pd.DataFrame,
    folds: tuple[WalkForwardFold, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    targets = rows["net_return_bps_nominal"].to_numpy(dtype=float)
    metric_rows: list[dict[str, object]] = []
    prediction_rows: list[pd.DataFrame] = []
    for fold in folds:
        predictions = _fold_predictions(features, targets, fold)
        for candidate, values in predictions.items():
            predicted_test, threshold = values
            actual = targets[fold.test_indices]
            metric_rows.append(
                _metric_row(candidate, fold, rows, actual, predicted_test, threshold)
            )
            prediction_rows.append(
                _prediction_frame(
                    candidate, fold, rows, actual, predicted_test, threshold
                )
            )
    return pd.DataFrame(metric_rows), pd.concat(prediction_rows, ignore_index=True)


def _fold_predictions(
    features: pd.DataFrame,
    targets: np.ndarray,
    fold: WalkForwardFold,
) -> dict[str, tuple[np.ndarray, float]]:
    train, test = fold.train_indices, fold.test_indices
    ridge = _ridge_pipeline().fit(features.iloc[train], targets[train])
    booster = lgb.train(
        return_lightgbm_params(),
        lgb.Dataset(features.iloc[train], label=targets[train]),
        num_boost_round=100,
    )
    predictions = {
        "ridge_net_return": (
            ridge.predict(features.iloc[train]),
            ridge.predict(features.iloc[test]),
        ),
        "lightgbm_net_return": (
            np.asarray(booster.predict(features.iloc[train]), dtype=float),
            np.asarray(booster.predict(features.iloc[test]), dtype=float),
        ),
    }
    return {
        name: (test_values, float(np.quantile(train_values, 0.80)))
        for name, (train_values, test_values) in predictions.items()
    }


def _ridge_pipeline() -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            ("model", Ridge(alpha=10.0)),
        ]
    )


def _metric_row(
    candidate: str,
    fold: WalkForwardFold,
    rows: pd.DataFrame,
    actual: np.ndarray,
    predicted: np.ndarray,
    threshold: float,
) -> dict[str, object]:
    test_rows = rows.iloc[fold.test_indices]
    rank_ics = _daily_rank_ics(test_rows, actual, predicted)
    baseline = float(np.median(rows.iloc[fold.train_indices]["net_return_bps_nominal"]))
    return {
        "candidate": candidate,
        "fold_id": fold.fold_id,
        "train_rows": len(fold.train_indices),
        "test_rows": len(fold.test_indices),
        "mae_bps": float(np.mean(np.abs(actual - predicted))),
        "baseline_mae_bps": float(np.mean(np.abs(actual - baseline))),
        "rmse_bps": float(np.sqrt(np.mean(np.square(actual - predicted)))),
        "daily_rank_ic_mean": float(rank_ics.mean()) if len(rank_ics) else None,
        "daily_rank_ic_median": float(rank_ics.median()) if len(rank_ics) else None,
        "positive_ic_days": int(rank_ics.gt(0.0).sum()),
        "ic_days": len(rank_ics),
        "selection_threshold_bps": threshold,
    }


def _daily_rank_ics(
    rows: pd.DataFrame, actual: np.ndarray, predicted: np.ndarray
) -> pd.Series:
    frame = pd.DataFrame(
        {
            "day": pd.to_datetime(rows["available_at_utc"], utc=True).dt.floor("D"),
            "actual": actual,
            "predicted": predicted,
        }
    )
    values: list[float] = []
    for _, day in frame.groupby("day", sort=True):
        if (
            len(day) >= 10
            and day["actual"].nunique() > 1
            and day["predicted"].nunique() > 1
        ):
            value = day["actual"].corr(day["predicted"], method="spearman")
            if math.isfinite(value):
                values.append(float(value))
    return pd.Series(values, dtype=float)


def _prediction_frame(
    candidate: str,
    fold: WalkForwardFold,
    rows: pd.DataFrame,
    actual: np.ndarray,
    predicted: np.ndarray,
    threshold: float,
) -> pd.DataFrame:
    columns = [
        "event_id",
        "symbol",
        "side",
        "available_at_utc",
        "entry_time_utc",
        "outcome_time_utc",
        "status",
    ]
    frame = rows.iloc[fold.test_indices][columns].reset_index(drop=True).copy()
    frame["fold_id"] = fold.fold_id
    frame["candidate"] = candidate
    frame["actual_net_bps"] = actual
    frame["prediction"] = predicted
    frame["selection_threshold_bps"] = threshold
    frame["clears_training_threshold"] = predicted >= threshold
    return frame


def _select_and_serialize(predictions: pd.DataFrame) -> pd.DataFrame:
    eligible = predictions.loc[predictions["clears_training_threshold"]].copy()
    choices: list[pd.Series] = []
    for _, group in eligible.groupby(["candidate", "event_id"], sort=True):
        ranked = group.sort_values("prediction", ascending=False)
        if len(ranked) > 1 and math.isclose(
            float(ranked.iloc[0]["prediction"]),
            float(ranked.iloc[1]["prediction"]),
            abs_tol=1e-12,
        ):
            continue
        choices.append(ranked.iloc[0])
    selected = pd.DataFrame(choices, columns=eligible.columns)
    if selected.empty:
        return selected.assign(accepted=False, displacement_reason=None)
    selected = selected.sort_values(["candidate", "symbol", "entry_time_utc"])
    return _serialize_choices(selected)


def _serialize_choices(selected: pd.DataFrame) -> pd.DataFrame:
    output = selected.copy()
    output["accepted"] = False
    output["displacement_reason"] = None
    occupied: dict[tuple[str, str], pd.Timestamp] = {}
    for index, row in output.iterrows():
        key = (str(row["candidate"]), str(row["symbol"]))
        entry = pd.Timestamp(row["entry_time_utc"])
        if entry < occupied.get(key, pd.Timestamp.min.tz_localize("UTC")):
            output.at[index, "displacement_reason"] = "symbol_position_open"
            continue
        output.at[index, "accepted"] = True
        occupied[key] = pd.Timestamp(row["outcome_time_utc"])
    return output.reset_index(drop=True)


def _candidate_summary(
    candidate: str, fold_metrics: pd.DataFrame, selected: pd.DataFrame
) -> dict[str, float | int | None]:
    folds = fold_metrics.loc[fold_metrics["candidate"].eq(candidate)]
    trades = selected.loc[selected["candidate"].eq(candidate) & selected["accepted"]]
    values = trades["actual_net_bps"].astype(float)
    profits = float(values.loc[values.gt(0.0)].sum())
    losses = float(-values.loc[values.lt(0.0)].sum())
    largest = float(values.max()) if len(values) else 0.0
    return {
        "folds": len(folds),
        "daily_rank_ic_mean": _optional_mean(folds["daily_rank_ic_mean"]),
        "positive_mean_ic_folds": int(folds["daily_rank_ic_mean"].gt(0.0).sum()),
        "mae_better_than_baseline_folds": int(
            folds["mae_bps"].lt(folds["baseline_mae_bps"]).sum()
        ),
        "selected_trades": len(values),
        "selected_net_bps": float(values.sum()),
        "selected_profit_factor": profits / losses if losses > 0.0 else None,
        "selected_net_ex_largest_winner_bps": float(values.sum() - max(largest, 0.0)),
    }


def _optional_mean(values: pd.Series) -> float | None:
    finite = values.dropna().astype(float)
    return float(finite.mean()) if len(finite) else None


def _timestamp_ms(values: pd.Series) -> int:
    return int(pd.Timestamp(values.iloc[0]).timestamp() * 1_000)


def _maximum_timestamp_ms(values: pd.Series) -> int:
    return int(pd.to_datetime(values, utc=True).max().timestamp() * 1_000)
