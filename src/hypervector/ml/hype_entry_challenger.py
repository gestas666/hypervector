"""Purged report-only return challengers for HYPE breakout entries."""

from __future__ import annotations

from dataclasses import dataclass
import math

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from hypervector.ml.hypervelocity_challenger import (
    WalkForwardFold,
    purged_walk_forward_folds,
)
from hypervector.research.hype_breakout_entry_features import (
    HYPE_ENTRY_ATTRIBUTION_FEATURES,
)

HYPE_ENTRY_MODEL_CANDIDATES: tuple[str, str] = (
    "ridge_return",
    "lightgbm_return",
)
_TAIL_FRACTION = 0.2


@dataclass(frozen=True)
class HypeEntryChallengerResult:
    """Exact OOS predictions, folds, metrics, and report-only verdicts."""

    rows: pd.DataFrame
    folds: tuple[WalkForwardFold, ...]
    fold_metrics: pd.DataFrame
    predictions: pd.DataFrame
    report: dict[str, object]


def evaluate_hype_entry_challengers(
    raw: pd.DataFrame,
    *,
    n_splits: int = 5,
    embargo_minutes: int = 60,
    modeled_round_trip_bps: float = 13.0,
) -> HypeEntryChallengerResult:
    """Evaluate fixed Ridge and shallow LightGBM without execution authority."""
    return evaluate_hype_entry_feature_set(
        raw,
        feature_names=HYPE_ENTRY_ATTRIBUTION_FEATURES,
        candidate_names=HYPE_ENTRY_MODEL_CANDIDATES,
        n_splits=n_splits,
        embargo_minutes=embargo_minutes,
        modeled_round_trip_bps=modeled_round_trip_bps,
    )


def evaluate_hype_entry_feature_set(
    raw: pd.DataFrame,
    *,
    feature_names: tuple[str, ...],
    candidate_names: tuple[str, str],
    n_splits: int = 5,
    embargo_minutes: int = 60,
    modeled_round_trip_bps: float = 13.0,
) -> HypeEntryChallengerResult:
    """Evaluate one frozen feature set with fixed Ridge and LightGBM."""
    if not feature_names or len(set(feature_names)) != len(feature_names):
        raise ValueError("HYPE entry feature names must be non-empty and unique")
    if len(set(candidate_names)) != 2:
        raise ValueError("HYPE entry candidate names must be unique")
    rows = _prepare_rows(raw, feature_names)
    if modeled_round_trip_bps <= 0.0:
        raise ValueError("modeled round-trip cost must be positive")
    folds = purged_walk_forward_folds(
        rows,
        n_splits=n_splits,
        embargo_minutes=embargo_minutes,
    )
    if len(folds) != n_splits:
        raise ValueError(f"HYPE entry challenger produced {len(folds)} folds")
    features = rows.loc[:, feature_names].astype(float)
    targets = rows["gross_return_bps"].to_numpy(dtype=float)
    metrics, predictions = _evaluate_folds(
        rows,
        features,
        targets,
        folds,
        candidate_names,
    )
    report = _build_report(
        rows,
        metrics,
        n_splits=n_splits,
        embargo_minutes=embargo_minutes,
        modeled_round_trip_bps=modeled_round_trip_bps,
        feature_names=feature_names,
        candidate_names=candidate_names,
    )
    return HypeEntryChallengerResult(rows, folds, metrics, predictions, report)


def fit_predict_entry_feature_set(
    training_raw: pd.DataFrame,
    confirmation_raw: pd.DataFrame,
    *,
    feature_names: tuple[str, ...],
    candidate_names: tuple[str, str],
) -> pd.DataFrame:
    """Fit fixed return models on training rows and predict later rows only."""
    if not feature_names or len(set(feature_names)) != len(feature_names):
        raise ValueError("entry feature names must be non-empty and unique")
    if len(set(candidate_names)) != 2:
        raise ValueError("entry candidate names must be unique")
    training = _prepare_rows(training_raw, feature_names)
    confirmation = _prepare_rows(confirmation_raw, feature_names)
    if training["outcome_ts_ms"].max() >= confirmation["signal_ts_ms"].min():
        raise ValueError("training outcomes must precede confirmation signals")
    combined = pd.concat((training, confirmation), ignore_index=True)
    features = combined.loc[:, feature_names].astype(float)
    targets = combined["gross_return_bps"].to_numpy(dtype=float)
    boundary = len(training)
    fold = WalkForwardFold(
        0,
        np.arange(boundary, dtype=int),
        np.arange(boundary, len(combined), dtype=int),
    )
    predictions = _fold_predictions(features, targets, fold, candidate_names)
    return pd.concat(
        (
            _prediction_frame(combined, targets, fold, name, values)
            for name, values in predictions.items()
        ),
        ignore_index=True,
    )


def _prepare_rows(raw: pd.DataFrame, feature_names: tuple[str, ...]) -> pd.DataFrame:
    required = {
        "entry_side",
        "signal_time_utc",
        "entry_time_utc",
        "exit_time_utc",
        "gross_return_bps",
        "net_return_bps",
        "exit_reason",
        *feature_names,
    }
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise ValueError(f"HYPE entry challenger rows missing: {missing}")
    if raw.empty:
        raise ValueError("HYPE entry challenger rows must be non-empty")
    rows = raw.copy().reset_index(drop=True)
    for name in ("signal_time_utc", "entry_time_utc", "exit_time_utc"):
        rows[name] = pd.to_datetime(rows[name], utc=True, errors="coerce")
    if rows[["signal_time_utc", "entry_time_utc", "exit_time_utc"]].isna().any().any():
        raise ValueError("HYPE entry timestamps must be valid UTC values")
    if not rows["signal_time_utc"].is_monotonic_increasing:
        raise ValueError("HYPE entry challenger rows must be chronologically ordered")
    if not rows["signal_time_utc"].is_unique:
        raise ValueError("HYPE entry signal timestamps must be unique")
    if (rows["entry_time_utc"] <= rows["signal_time_utc"]).any():
        raise ValueError("HYPE entry fills must follow their signals")
    if (rows["exit_time_utc"] < rows["entry_time_utc"]).any():
        raise ValueError("HYPE entry outcomes cannot precede entry fills")
    if not rows["entry_side"].isin(("long", "short")).all():
        raise ValueError("HYPE entry side must be long or short")
    numeric = rows.loc[
        :,
        [
            *feature_names,
            "gross_return_bps",
            "net_return_bps",
        ],
    ].astype(float)
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("HYPE entry model features and returns must be finite")
    rows["signal_ts_ms"] = _timestamps_ms(rows["signal_time_utc"])
    rows["outcome_ts_ms"] = _timestamps_ms(rows["exit_time_utc"])
    return rows


def _timestamps_ms(values: pd.Series) -> pd.Series:
    nanoseconds = values.astype("datetime64[ns, UTC]").astype("int64")
    return nanoseconds // 1_000_000


def _evaluate_folds(
    rows: pd.DataFrame,
    features: pd.DataFrame,
    targets: np.ndarray,
    folds: tuple[WalkForwardFold, ...],
    candidate_names: tuple[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    metric_rows: list[dict[str, object]] = []
    prediction_rows: list[pd.DataFrame] = []
    for fold in folds:
        predictions = _fold_predictions(
            features,
            targets,
            fold,
            candidate_names,
        )
        for candidate, predicted in predictions.items():
            metric_rows.append(_fold_metrics(rows, targets, fold, candidate, predicted))
            prediction_rows.append(
                _prediction_frame(rows, targets, fold, candidate, predicted)
            )
    return pd.DataFrame(metric_rows), pd.concat(prediction_rows, ignore_index=True)


def _fold_predictions(
    features: pd.DataFrame,
    targets: np.ndarray,
    fold: WalkForwardFold,
    candidate_names: tuple[str, str],
) -> dict[str, np.ndarray]:
    train, test = fold.train_indices, fold.test_indices
    ridge = Pipeline([("scale", StandardScaler()), ("model", Ridge(alpha=10.0))]).fit(
        features.iloc[train], targets[train]
    )
    booster = lgb.train(
        _lightgbm_params(),
        lgb.Dataset(features.iloc[train], label=targets[train]),
        num_boost_round=100,
    )
    return {
        candidate_names[0]: np.asarray(
            ridge.predict(features.iloc[test]),
            dtype=float,
        ),
        candidate_names[1]: np.asarray(
            booster.predict(features.iloc[test]),
            dtype=float,
        ),
    }


def _lightgbm_params() -> dict[str, float | int | str | bool]:
    return {
        "objective": "regression",
        "metric": "l2",
        "learning_rate": 0.03,
        "num_leaves": 7,
        "max_depth": 3,
        "min_data_in_leaf": 40,
        "lambda_l2": 2.0,
        "feature_fraction": 1.0,
        "bagging_fraction": 1.0,
        "bagging_freq": 0,
        "seed": 42,
        "num_threads": 1,
        "deterministic": True,
        "force_col_wise": True,
        "verbose": -1,
    }


def _fold_metrics(
    rows: pd.DataFrame,
    targets: np.ndarray,
    fold: WalkForwardFold,
    candidate: str,
    predicted: np.ndarray,
) -> dict[str, object]:
    test = fold.test_indices
    actual_gross = targets[test]
    actual_net = rows.iloc[test]["net_return_bps"].to_numpy(dtype=float)
    count = max(1, math.ceil(_TAIL_FRACTION * len(test)))
    order = np.argsort(predicted, kind="stable")
    low, high = order[:count], order[-count:]
    error = predicted - actual_gross
    baseline = np.full(len(test), float(np.mean(targets[fold.train_indices])))
    return {
        "candidate": candidate,
        "fold_id": fold.fold_id,
        "train_samples": len(fold.train_indices),
        "test_samples": len(test),
        "test_start_utc": rows.iloc[test[0]]["signal_time_utc"].isoformat(),
        "test_end_utc": rows.iloc[test[-1]]["signal_time_utc"].isoformat(),
        "mae_bps": float(np.mean(np.abs(error))),
        "rmse_bps": float(np.sqrt(np.mean(np.square(error)))),
        "baseline_mae_bps": float(np.mean(np.abs(baseline - actual_gross))),
        "rank_ic": _rank_ic(actual_gross, predicted),
        "selected_rows": count,
        "top_mean_gross_bps": float(np.mean(actual_gross[high])),
        "bottom_mean_gross_bps": float(np.mean(actual_gross[low])),
        "gross_tail_spread_bps": float(
            np.mean(actual_gross[high]) - np.mean(actual_gross[low])
        ),
        "top_mean_net_bps": float(np.mean(actual_net[high])),
        "bottom_mean_net_bps": float(np.mean(actual_net[low])),
        "top_positive_net_rate": float(np.mean(actual_net[high] > 0.0)),
    }


def _rank_ic(actual: np.ndarray, predicted: np.ndarray) -> float:
    if np.ptp(actual) <= 1e-12 or np.ptp(predicted) <= 1e-12:
        return float("nan")
    return float(pd.Series(actual).corr(pd.Series(predicted), method="spearman"))


def _prediction_frame(
    rows: pd.DataFrame,
    targets: np.ndarray,
    fold: WalkForwardFold,
    candidate: str,
    predicted: np.ndarray,
) -> pd.DataFrame:
    test = fold.test_indices
    frame = rows.iloc[test][
        ["signal_time_utc", "exit_time_utc", "entry_side", "exit_reason"]
    ].reset_index(drop=True)
    frame["fold_id"] = fold.fold_id
    frame["candidate"] = candidate
    frame["actual_gross_return_bps"] = targets[test]
    frame["actual_net_return_bps"] = rows.iloc[test]["net_return_bps"].to_numpy()
    frame["predicted_gross_return_bps"] = predicted
    return frame


def _build_report(
    rows: pd.DataFrame,
    metrics: pd.DataFrame,
    *,
    n_splits: int,
    embargo_minutes: int,
    modeled_round_trip_bps: float,
    feature_names: tuple[str, ...],
    candidate_names: tuple[str, str],
) -> dict[str, object]:
    hurdle = 2.0 * modeled_round_trip_bps
    candidates = {
        name: _candidate_summary(
            metrics.loc[metrics["candidate"].eq(name)], hurdle, n_splits
        )
        for name in candidate_names
    }
    selected = _supported_candidate(candidates, candidate_names)
    return {
        "schema_version": 1,
        "mode": "hype_entry_return_model_development_v1",
        "contract": _report_only_contract(),
        "dataset": _dataset_report(rows, feature_names),
        "walk_forward": {
            "folds": n_splits,
            "embargo_minutes": embargo_minutes,
            "outcome_timestamp_purged": True,
            "transforms_fit_inside_each_fold": True,
        },
        "trial_accounting": {
            "model_candidates": len(candidate_names),
            "candidate_names": list(candidate_names),
            "features_fixed_before_scoring": len(feature_names),
            "hyperparameter_sweeps": 0,
        },
        "acceptance": _acceptance_report(n_splits, hurdle),
        "candidates": candidates,
        "forward_candidate": {
            "candidate": selected,
            "status": (
                "development_supported_requires_prospective_observation"
                if selected
                else "no_supported_candidate"
            ),
            "live_authority": False,
        },
        "limitations": _limitations(),
    }


def _supported_candidate(
    candidates: dict[str, dict[str, object]],
    candidate_names: tuple[str, ...],
) -> str | None:
    supported = [
        name for name in candidate_names if candidates[name]["development_supported"]
    ]
    if not supported:
        return None
    return max(
        supported,
        key=lambda name: _candidate_top_net(candidates[name]),
    )


def _candidate_top_net(candidate: dict[str, object]) -> float:
    value = candidate.get("median_top_net_bps")
    if not isinstance(value, int | float):
        raise ValueError("HYPE entry candidate top-net metric must be numeric")
    return float(value)


def _report_only_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_promotion": False,
    }


def _dataset_report(
    rows: pd.DataFrame,
    feature_names: tuple[str, ...],
) -> dict[str, object]:
    overlaps = int(
        (rows["signal_time_utc"].shift(-1) < rows["exit_time_utc"]).iloc[:-1].sum()
    )
    return {
        "rows": len(rows),
        "start_utc": rows.iloc[0]["signal_time_utc"].isoformat(),
        "end_utc": rows.iloc[-1]["signal_time_utc"].isoformat(),
        "overlapping_lifecycle_pairs": overlaps,
        "features": list(feature_names),
        "training_target": "gross_return_bps",
        "economic_evaluation": "actual_net_return_bps",
    }


def _acceptance_report(n_splits: int, hurdle: float) -> dict[str, object]:
    return {
        "positive_rank_ic_folds_required": math.ceil(0.8 * n_splits),
        "maximum_worst_fold_rank_ic": -0.05,
        "gross_spread_hurdle_bps": hurdle,
        "spread_and_top_net_folds_required": math.ceil(0.6 * n_splits),
    }


def _limitations() -> list[str]:
    return [
        "development evidence cannot establish prospective executable edge",
        "serial market regimes remain dependent despite non-overlapping lifecycles",
        "bar-derived entry features do not reproduce event-level queue position",
        "the final opened holdout is not read or rescored by this evaluator",
    ]


def _candidate_summary(
    rows: pd.DataFrame,
    hurdle: float,
    n_splits: int,
) -> dict[str, object]:
    rank = rows["rank_ic"].dropna().astype(float)
    spread = rows["gross_tail_spread_bps"].astype(float)
    top_net = rows["top_mean_net_bps"].astype(float)
    required_rank = math.ceil(0.8 * n_splits)
    required_economic = math.ceil(0.6 * n_splits)
    checks = {
        "rank_sign_consistent": int((rank > 0.0).sum()) >= required_rank,
        "rank_worst_fold_above_floor": not rank.empty and float(rank.min()) > -0.05,
        "median_spread_clears_hurdle": float(spread.median()) >= hurdle,
        "spread_clearing_folds": int((spread >= hurdle).sum()) >= required_economic,
        "positive_top_net_folds": int((top_net > 0.0).sum()) >= required_economic,
    }
    return {
        "valid_rank_ic_folds": len(rank),
        "positive_rank_ic_folds": int((rank > 0.0).sum()),
        "median_rank_ic": _optional_stat(rank, "median"),
        "rank_ic_iqr": (
            float(rank.quantile(0.75) - rank.quantile(0.25)) if not rank.empty else None
        ),
        "worst_fold_rank_ic": _optional_stat(rank, "min"),
        "median_mae_bps": float(rows["mae_bps"].median()),
        "median_baseline_mae_bps": float(rows["baseline_mae_bps"].median()),
        "gross_spread_hurdle_bps": hurdle,
        "median_gross_tail_spread_bps": float(spread.median()),
        "worst_gross_tail_spread_bps": float(spread.min()),
        "spread_clearing_folds": int((spread >= hurdle).sum()),
        "median_top_net_bps": float(top_net.median()),
        "worst_top_net_bps": float(top_net.min()),
        "positive_top_net_folds": int((top_net > 0.0).sum()),
        "support_checks": checks,
        "development_supported": all(checks.values()),
    }


def _optional_stat(values: pd.Series, method: str) -> float | None:
    if values.empty:
        return None
    return float(getattr(values, method)())
