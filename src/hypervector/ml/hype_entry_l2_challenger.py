"""Predeclared bar/L2 return challengers for HYPE breakout entries."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from hypervector.ml.hype_entry_challenger import (
    HypeEntryChallengerResult,
    evaluate_hype_entry_feature_set,
)
from hypervector.ml.hypervelocity_challenger import WalkForwardFold
from hypervector.research.hype_breakout_entry_features import (
    HYPE_ENTRY_ATTRIBUTION_FEATURES,
)
from hypervector.research.hype_entry_l2_features import HYPE_ENTRY_L2_FEATURES

HYPE_ENTRY_L2_MODEL_CANDIDATES: tuple[str, ...] = (
    "bar_ridge_return",
    "bar_lightgbm_return",
    "l2_ridge_return",
    "l2_lightgbm_return",
    "combined_ridge_return",
    "combined_lightgbm_return",
)

_FEATURE_SETS: tuple[tuple[str, tuple[str, ...], tuple[str, str]], ...] = (
    (
        "bar_only",
        HYPE_ENTRY_ATTRIBUTION_FEATURES,
        ("bar_ridge_return", "bar_lightgbm_return"),
    ),
    (
        "l2_only",
        HYPE_ENTRY_L2_FEATURES,
        ("l2_ridge_return", "l2_lightgbm_return"),
    ),
    (
        "bar_plus_l2",
        HYPE_ENTRY_ATTRIBUTION_FEATURES + HYPE_ENTRY_L2_FEATURES,
        ("combined_ridge_return", "combined_lightgbm_return"),
    ),
)


@dataclass(frozen=True)
class HypeEntryL2ChallengerResult:
    """Six-candidate OOS evidence with one shared temporal fold contract."""

    rows: pd.DataFrame
    folds: tuple[WalkForwardFold, ...]
    fold_metrics: pd.DataFrame
    predictions: pd.DataFrame
    report: dict[str, object]


def evaluate_hype_entry_l2_challengers(
    raw: pd.DataFrame,
    *,
    n_splits: int = 5,
    embargo_minutes: int = 60,
    modeled_round_trip_bps: float = 13.0,
) -> HypeEntryL2ChallengerResult:
    """Compare frozen bar-only, L2-only, and combined model pairs."""
    results = tuple(
        _evaluate_set(
            raw,
            features,
            candidates,
            n_splits,
            embargo_minutes,
            modeled_round_trip_bps,
        )
        for _, features, candidates in _FEATURE_SETS
    )
    _validate_shared_folds(results)
    metrics = pd.concat([value.fold_metrics for value in results], ignore_index=True)
    predictions = pd.concat(
        [value.predictions for value in results],
        ignore_index=True,
    )
    report = _combined_report(results, modeled_round_trip_bps)
    return HypeEntryL2ChallengerResult(
        results[0].rows,
        results[0].folds,
        metrics,
        predictions,
        report,
    )


def _evaluate_set(
    raw: pd.DataFrame,
    features: tuple[str, ...],
    candidates: tuple[str, str],
    n_splits: int,
    embargo_minutes: int,
    modeled_round_trip_bps: float,
) -> HypeEntryChallengerResult:
    return evaluate_hype_entry_feature_set(
        raw,
        feature_names=features,
        candidate_names=candidates,
        n_splits=n_splits,
        embargo_minutes=embargo_minutes,
        modeled_round_trip_bps=modeled_round_trip_bps,
    )


def _validate_shared_folds(
    results: tuple[HypeEntryChallengerResult, ...],
) -> None:
    reference = results[0].folds
    for result in results[1:]:
        if len(result.folds) != len(reference):
            raise ValueError("HYPE entry feature sets produced different fold counts")
        for left, right in zip(reference, result.folds, strict=True):
            equal = np.array_equal(left.train_indices, right.train_indices)
            equal &= np.array_equal(left.test_indices, right.test_indices)
            if left.fold_id != right.fold_id or not equal:
                raise ValueError("HYPE entry feature sets produced different folds")


def _combined_report(
    results: tuple[HypeEntryChallengerResult, ...],
    modeled_round_trip_bps: float,
) -> dict[str, object]:
    candidates: dict[str, object] = {}
    for result in results:
        value = result.report.get("candidates")
        if not isinstance(value, dict):
            raise ValueError("HYPE entry feature-set report has no candidates")
        candidates.update(value)
    selected = _supported_candidate(candidates)
    base = results[0].report
    return {
        "schema_version": 1,
        "mode": "hype_entry_l2_return_model_development_v1",
        "contract": base["contract"],
        "dataset": _dataset_report(results[0].rows),
        "walk_forward": base["walk_forward"],
        "trial_accounting": {
            "model_candidates": len(HYPE_ENTRY_L2_MODEL_CANDIDATES),
            "candidate_names": list(HYPE_ENTRY_L2_MODEL_CANDIDATES),
            "feature_sets": len(_FEATURE_SETS),
            "hyperparameter_sweeps": 0,
        },
        "acceptance": base["acceptance"],
        "modeled_round_trip_bps": modeled_round_trip_bps,
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


def _dataset_report(rows: pd.DataFrame) -> dict[str, object]:
    return {
        "rows": len(rows),
        "start_utc": rows.iloc[0]["signal_time_utc"].isoformat(),
        "end_utc": rows.iloc[-1]["signal_time_utc"].isoformat(),
        "feature_sets": {name: list(features) for name, features, _ in _FEATURE_SETS},
        "training_target": "gross_return_bps",
        "economic_evaluation": "actual_net_return_bps",
    }


def _supported_candidate(candidates: dict[str, object]) -> str | None:
    supported = [
        name
        for name in HYPE_ENTRY_L2_MODEL_CANDIDATES
        if _candidate_supported(candidates[name])
    ]
    if not supported:
        return None
    return max(supported, key=lambda name: _candidate_top_net(candidates[name]))


def _candidate_supported(value: object) -> bool:
    return isinstance(value, dict) and value.get("development_supported") is True


def _candidate_top_net(value: object) -> float:
    if not isinstance(value, dict):
        raise ValueError("HYPE entry candidate report must be an object")
    return float(value["median_top_net_bps"])


def _limitations() -> list[str]:
    return [
        "development evidence cannot establish prospective executable edge",
        "65 vendor-gap entries are excluded rather than imputed",
        "vendor-covered and excluded outcomes are not assumed exchangeable",
        "post-entry L2 observations are diagnostics and never model inputs",
        "the final opened holdout is not read or rescored by this evaluator",
    ]
