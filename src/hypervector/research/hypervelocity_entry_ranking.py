"""Point-in-time datasets for observe-only creator entry-time ranking."""

from __future__ import annotations

from dataclasses import dataclass
import math

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from hypervector.research.hypervelocity_metalabel import BASE_FEATURE_NAMES

_DIRECTIONS = ("long", "short")
_SOURCE_COLUMNS = {"source_id", "event_time", "side"}
RANKING_MODEL_NAMES: tuple[str, ...] = (
    "uniform",
    "strength_only",
    "logistic",
    "lightgbm",
)
_TOP_FRACTIONS = (0.01, 0.05, 0.10, 0.20)


@dataclass(frozen=True)
class EntryRankingDataset:
    """Candidate minutes and their independently audited source alignment."""

    candidates: pd.DataFrame
    source_alignment: pd.DataFrame


@dataclass(frozen=True)
class EntryRankingResult:
    """Out-of-sample scores and diagnostics for the frozen searched set."""

    searched_set: tuple[str, ...]
    fold_audit: pd.DataFrame
    fold_metrics: pd.DataFrame
    predictions: pd.DataFrame
    summary: dict[str, dict[str, float | int | None]]


@dataclass(frozen=True)
class _DayFold:
    test_day_utc: str
    train_indices: np.ndarray
    test_indices: np.ndarray


def _validate_candidates(candidates: pd.DataFrame) -> None:
    required = {"direction", *BASE_FEATURE_NAMES}
    missing = required.difference(candidates.columns)
    if missing:
        raise ValueError(f"candidate features missing: {sorted(missing)}")
    if candidates.empty:
        raise ValueError("candidate features must not be empty")
    if not isinstance(candidates.index, pd.DatetimeIndex):
        raise ValueError("candidate index must be a DatetimeIndex")
    if candidates.index.tz is None:
        raise ValueError("candidate index must be timezone-aware")
    if not candidates.index.is_monotonic_increasing:
        raise ValueError("candidate index must be monotonic increasing")
    if not candidates.index.is_unique:
        raise ValueError("candidate index must be unique")
    if not candidates["direction"].isin(_DIRECTIONS).all():
        raise ValueError("candidate direction must be long or short")


def _parse_source(source_entries: pd.DataFrame) -> pd.DataFrame:
    missing = _SOURCE_COLUMNS.difference(source_entries.columns)
    if missing:
        raise ValueError(f"source entries missing columns: {sorted(missing)}")
    parsed = source_entries.copy(deep=True)
    if parsed.empty:
        raise ValueError("source entries must not be empty")
    if parsed["source_id"].isna().any() or not parsed["source_id"].is_unique:
        raise ValueError("source_id values must be present and unique")
    if not parsed["side"].isin(_DIRECTIONS).all():
        raise ValueError("source side must be long or short")
    try:
        parsed["event_time"] = pd.to_datetime(
            parsed["event_time"], utc=True, format="ISO8601"
        )
    except (TypeError, ValueError) as error:
        raise ValueError("source event_time must be valid ISO8601") from error
    return parsed


def _minute_mapping(
    source: pd.DataFrame,
    candidate_index: pd.DatetimeIndex,
    evidence_start: pd.Timestamp | None,
    evidence_end: pd.Timestamp | None,
) -> pd.DatetimeIndex:
    event_times = pd.DatetimeIndex(source["event_time"])
    if (evidence_start is None) != (evidence_end is None):
        raise ValueError("evidence_start and evidence_end must be supplied together")
    first = candidate_index[0] if evidence_start is None else evidence_start
    final_exclusive = (
        candidate_index[-1] + pd.Timedelta(minutes=1)
        if evidence_end is None
        else evidence_end
    )
    if first.tzinfo is None or final_exclusive.tzinfo is None:
        raise ValueError("evidence bounds must be timezone-aware")
    if first >= final_exclusive:
        raise ValueError("evidence end must follow evidence start")
    if candidate_index[0] < first or candidate_index[-1] >= final_exclusive:
        raise ValueError("candidate minutes fall outside evidence bounds")
    if (event_times < first).any() or (event_times >= final_exclusive).any():
        raise ValueError("source event_time is outside candidate bounds")
    minute_index = event_times.floor("min")
    keys = pd.MultiIndex.from_arrays([minute_index, source["side"]])
    if keys.has_duplicates:
        raise ValueError("multiple source entries map to the same candidate minute")
    return minute_index


def build_entry_ranking_dataset(
    candidates: pd.DataFrame,
    source_entries: pd.DataFrame,
    *,
    evidence_start: pd.Timestamp | None = None,
    evidence_end: pd.Timestamp | None = None,
) -> EntryRankingDataset:
    """Map creator entries to exact completed candidate minutes without negatives."""
    _validate_candidates(candidates)
    source = _parse_source(source_entries)
    minute_index = _minute_mapping(
        source,
        candidates.index,
        evidence_start,
        evidence_end,
    )

    labeled = candidates.copy(deep=True)
    labeled["is_observed_entry"] = False
    labeled["label_kind"] = "unlabeled"
    labeled["source_id"] = pd.Series(pd.NA, index=labeled.index, dtype="object")

    alignment_rows: list[dict[str, object]] = []
    for row_number, (_, entry) in enumerate(source.iterrows()):
        minute = minute_index[row_number]
        has_candidate = minute in labeled.index
        mapped_direction = (
            str(labeled.at[minute, "direction"]) if has_candidate else None
        )
        matched = has_candidate and mapped_direction == entry["side"]
        reason = "matched" if matched else "direction_mismatch"
        if not has_candidate:
            reason = "no_candidate_at_minute"
        if matched:
            labeled.at[minute, "is_observed_entry"] = True
            labeled.at[minute, "label_kind"] = "observed_entry"
            labeled.at[minute, "source_id"] = str(entry["source_id"])
        alignment_rows.append(
            {
                "source_id": str(entry["source_id"]),
                "event_time_utc": entry["event_time"].isoformat(),
                "side": str(entry["side"]),
                "mapped_candidate_time_utc": minute.isoformat(),
                "mapped_direction": mapped_direction,
                "matched_direction": matched,
                "reason": reason,
            }
        )
    alignment = pd.DataFrame(alignment_rows)
    return EntryRankingDataset(candidates=labeled, source_alignment=alignment)


def _day_folds(rows: pd.DataFrame) -> tuple[_DayFold, ...]:
    utc_index = rows.index.tz_convert("UTC")
    days = utc_index.normalize()
    unique_days = days.unique().sort_values()
    labels = rows["is_observed_entry"].astype(int).to_numpy()
    folds: list[_DayFold] = []
    for day in unique_days[1:]:
        train = np.flatnonzero(days < day)
        test = np.flatnonzero(days == day)
        if len(test) and len(np.unique(labels[train])) == 2:
            folds.append(
                _DayFold(
                    test_day_utc=day.strftime("%Y-%m-%d"),
                    train_indices=train,
                    test_indices=test,
                )
            )
    if not folds:
        raise ValueError("no day-forward fold has both training classes")
    return tuple(folds)


def _feature_frame(rows: pd.DataFrame) -> pd.DataFrame:
    try:
        features = rows.loc[:, BASE_FEATURE_NAMES].astype(float)
    except (TypeError, ValueError) as error:
        raise ValueError("candidate features must be numeric") from error
    if np.isinf(features.to_numpy()).any():
        raise ValueError("candidate features must not contain infinity")
    return features


def _logistic_pipeline() -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    C=0.1,
                    class_weight="balanced",
                    max_iter=1_000,
                    random_state=42,
                ),
            ),
        ]
    )


def _logistic_scores(
    train: pd.DataFrame,
    labels: np.ndarray,
    test: pd.DataFrame,
) -> np.ndarray:
    model = _logistic_pipeline().fit(train, labels)
    return np.asarray(model.predict_proba(test)[:, 1], dtype=float)


def _lightgbm_scores(
    train: pd.DataFrame,
    labels: np.ndarray,
    test: pd.DataFrame,
) -> np.ndarray:
    positives = int(labels.sum())
    negatives = len(labels) - positives
    params: dict[str, float | int | str | bool] = {
        "objective": "binary",
        "metric": "binary_logloss",
        "learning_rate": 0.03,
        "num_leaves": 7,
        "max_depth": 3,
        "min_data_in_leaf": 5,
        "lambda_l2": 2.0,
        "scale_pos_weight": negatives / positives,
        "seed": 42,
        "num_threads": 1,
        "deterministic": True,
        "force_col_wise": True,
        "verbose": -1,
    }
    booster = lgb.train(
        params,
        lgb.Dataset(train, label=labels),
        num_boost_round=100,
    )
    return np.asarray(booster.predict(test), dtype=float)


def _fold_scores(
    features: pd.DataFrame,
    labels: np.ndarray,
    fold: _DayFold,
) -> dict[str, np.ndarray]:
    train = features.iloc[fold.train_indices]
    test = features.iloc[fold.test_indices]
    train_labels = labels[fold.train_indices]
    strength = test["regime_strength_percentile"].fillna(-1e12).to_numpy()
    return {
        "uniform": np.zeros(len(test), dtype=float),
        "strength_only": np.asarray(strength, dtype=float),
        "logistic": _logistic_scores(train, train_labels, test),
        "lightgbm": _lightgbm_scores(train, train_labels, test),
    }


def _percentile_scores(scores: pd.Series) -> pd.Series:
    if len(scores) == 1:
        return pd.Series(0.5, index=scores.index, dtype=float)
    ranks = scores.rank(method="average", ascending=True)
    return (ranks - 1.0) / (len(scores) - 1.0)


def _selection_probabilities(scores: np.ndarray, fraction: float) -> np.ndarray:
    count = max(1, math.ceil(len(scores) * fraction))
    threshold = np.sort(scores)[::-1][count - 1]
    above = scores > threshold
    tied = scores == threshold
    tie_probability = (count - int(above.sum())) / int(tied.sum())
    return np.where(above, 1.0, np.where(tied, tie_probability, 0.0))


def _prediction_frame(
    rows: pd.DataFrame,
    fold: _DayFold,
    model: str,
    scores: np.ndarray,
) -> pd.DataFrame:
    test = rows.iloc[fold.test_indices]
    result = pd.DataFrame(
        {
            "candidate_time_utc": [value.isoformat() for value in test.index],
            "test_day_utc": fold.test_day_utc,
            "direction": test["direction"].to_numpy(),
            "is_observed_entry": test["is_observed_entry"].to_numpy(),
            "model": model,
            "score": scores,
        }
    )
    result["positive_percentile"] = result.groupby("direction", sort=False)[
        "score"
    ].transform(_percentile_scores)
    return result


def _optional_rank_metrics(
    labels: np.ndarray,
    scores: np.ndarray,
) -> tuple[float, float]:
    if len(np.unique(labels)) < 2:
        return float("nan"), float("nan")
    return (
        float(roc_auc_score(labels, scores)),
        float(average_precision_score(labels, scores)),
    )


def _top_recall(frame: pd.DataFrame, fraction: float) -> float:
    positives = frame["is_observed_entry"].to_numpy(dtype=bool)
    if not positives.any():
        return float("nan")
    probabilities = np.zeros(len(frame), dtype=float)
    for _, positions in frame.groupby("direction", sort=False).indices.items():
        index = np.asarray(positions, dtype=int)
        probabilities[index] = _selection_probabilities(
            frame.iloc[index]["score"].to_numpy(dtype=float), fraction
        )
    return float(probabilities[positives].mean())


def _fold_metric(frame: pd.DataFrame, train_labels: np.ndarray) -> dict[str, object]:
    labels = frame["is_observed_entry"].to_numpy(dtype=int)
    scores = frame["score"].to_numpy(dtype=float)
    positive_percentiles = frame.loc[frame["is_observed_entry"], "positive_percentile"]
    auc, average_precision = _optional_rank_metrics(labels, scores)
    result: dict[str, object] = {
        "model": str(frame["model"].iloc[0]),
        "test_day_utc": str(frame["test_day_utc"].iloc[0]),
        "train_samples": len(train_labels),
        "train_positives": int(train_labels.sum()),
        "test_samples": len(labels),
        "test_positives": int(labels.sum()),
        "positive_percentile_mean": positive_percentiles.mean(),
        "positive_percentile_median": positive_percentiles.median(),
        "roc_auc": auc,
        "average_precision": average_precision,
    }
    for fraction in _TOP_FRACTIONS:
        result[f"top_{int(fraction * 100)}pct_recall"] = _top_recall(frame, fraction)
    return result


def _fold_audit(rows: pd.DataFrame, folds: tuple[_DayFold, ...]) -> pd.DataFrame:
    labels = rows["is_observed_entry"].astype(int).to_numpy()
    return pd.DataFrame(
        [
            {
                "test_day_utc": fold.test_day_utc,
                "train_days": int(rows.index[fold.train_indices].normalize().nunique()),
                "train_samples": len(fold.train_indices),
                "train_positives": int(labels[fold.train_indices].sum()),
                "train_max_time_utc": rows.index[fold.train_indices[-1]].isoformat(),
                "test_samples": len(fold.test_indices),
                "test_positives": int(labels[fold.test_indices].sum()),
            }
            for fold in folds
        ]
    )


def _finite_stat(values: pd.Series, operation: str) -> float | None:
    finite = values.dropna().astype(float)
    if finite.empty:
        return None
    if operation == "median":
        return float(finite.median())
    if operation == "minimum":
        return float(finite.min())
    return float(finite.mean())


def _summarize(metrics: pd.DataFrame) -> dict[str, dict[str, float | int | None]]:
    result: dict[str, dict[str, float | int | None]] = {}
    for model in RANKING_MODEL_NAMES:
        group = metrics.loc[metrics["model"].eq(model)]
        result[model] = {
            "folds_total": len(group),
            "folds_with_positive": int(group["test_positives"].gt(0).sum()),
            "oos_positives": int(group["test_positives"].sum()),
            "positive_percentile_median": _finite_stat(
                group["positive_percentile_median"], "median"
            ),
            "worst_fold_positive_percentile": _finite_stat(
                group["positive_percentile_mean"], "minimum"
            ),
            "top_10pct_recall_mean": _finite_stat(group["top_10pct_recall"], "mean"),
            "roc_auc_mean": _finite_stat(group["roc_auc"], "mean"),
            "average_precision_mean": _finite_stat(group["average_precision"], "mean"),
        }
    return result


def evaluate_entry_ranking(dataset: EntryRankingDataset) -> EntryRankingResult:
    """Evaluate fixed baselines and models on expanding UTC-day-forward folds."""
    rows = dataset.candidates
    _validate_candidates(rows)
    if "is_observed_entry" not in rows:
        raise ValueError("entry ranking candidates are missing observed labels")
    features = _feature_frame(rows)
    labels = rows["is_observed_entry"].astype(int).to_numpy()
    folds = _day_folds(rows)
    predictions: list[pd.DataFrame] = []
    metrics: list[dict[str, object]] = []
    for fold in folds:
        train_labels = labels[fold.train_indices]
        for model, scores in _fold_scores(features, labels, fold).items():
            frame = _prediction_frame(rows, fold, model, scores)
            predictions.append(frame)
            metrics.append(_fold_metric(frame, train_labels))
    prediction_frame = pd.concat(predictions, ignore_index=True)
    metric_frame = pd.DataFrame(metrics)
    return EntryRankingResult(
        searched_set=RANKING_MODEL_NAMES,
        fold_audit=_fold_audit(rows, folds),
        fold_metrics=metric_frame,
        predictions=prediction_frame,
        summary=_summarize(metric_frame),
    )
