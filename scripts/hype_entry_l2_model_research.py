#!/usr/bin/env python3
"""Score the predeclared six-way HYPE bar/L2 model comparison."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
    write_immutable_parquet,
)
from hypervector.ml.hype_entry_l2_challenger import (
    HYPE_ENTRY_L2_MODEL_CANDIDATES,
    HypeEntryL2ChallengerResult,
    evaluate_hype_entry_l2_challengers,
)
from hypervector.research.hype_breakout_entry_features import (
    HYPE_ENTRY_ATTRIBUTION_FEATURES,
)
from hypervector.research.hype_entry_l2_features import HYPE_ENTRY_L2_FEATURES

_DEFAULT_FEATURES = Path(
    "data/logs/research/"
    "hype_breakout_entry_l2_features_development_v1_20260806.features.parquet"
)
_DEFAULT_PLAN = Path(
    "data/logs/research/hype_breakout_entry_l2_model_plan_v1_20260806.json"
)
_DEFAULT_MATERIALIZATION = Path(
    "data/logs/research/hype_breakout_entry_l2_features_development_v1_20260806.json"
)


@dataclass(frozen=True)
class _PlanSettings:
    folds: int
    embargo_minutes: int
    modeled_round_trip_bps: float


@dataclass(frozen=True)
class _ResearchRun:
    result: HypeEntryL2ChallengerResult
    plan: dict[str, object]
    materialization: dict[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build a command with data paths only; model choices stay frozen."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=_DEFAULT_FEATURES)
    parser.add_argument("--plan", type=Path, default=_DEFAULT_PLAN)
    parser.add_argument(
        "--materialization-summary",
        type=Path,
        default=_DEFAULT_MATERIALIZATION,
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def output_paths(out: Path) -> tuple[Path, Path, Path]:
    """Return summary, fold-metric, and OOS-prediction paths."""
    if out.suffix != ".json":
        raise ValueError("HYPE L2 model output must use .json")
    return (
        out,
        out.with_suffix(".folds.parquet"),
        out.with_suffix(".predictions.parquet"),
    )


def run(args: argparse.Namespace) -> _ResearchRun:
    """Validate the frozen plan and score its exact six candidates."""
    for path in (args.features, args.plan, args.materialization_summary):
        _require_file(path)
    plan = _resolve_plan(_read_object(args.plan))
    materialization = _read_object(args.materialization_summary)
    settings = _validate_plan(plan, args.features)
    _validate_materialization(
        materialization,
        args.features,
        plan,
        args.materialization_summary,
    )
    rows = pd.read_parquet(args.features)
    result = evaluate_hype_entry_l2_challengers(
        rows,
        n_splits=settings.folds,
        embargo_minutes=settings.embargo_minutes,
        modeled_round_trip_bps=settings.modeled_round_trip_bps,
    )
    return _ResearchRun(result, plan, materialization)


def main() -> None:
    """Publish immutable OOS sidecars before their hash-linked report."""
    args = build_parser().parse_args()
    summary_path, folds_path, predictions_path = output_paths(args.out)
    for path in (summary_path, folds_path, predictions_path):
        _require_absent(path)
    run_result = run(args)
    result = run_result.result
    write_immutable_parquet(folds_path, result.fold_metrics)
    write_immutable_parquet(predictions_path, result.predictions)
    report = dict(result.report)
    report["predeclared_plan_evidence"] = _evidence(args.plan)
    report["materialization_evidence"] = _evidence(args.materialization_summary)
    report["data_evidence"] = {
        **_evidence(args.features),
        "rows": len(result.rows),
    }
    report["selection_bias"] = run_result.materialization["selection_bias"]
    report["fold_evidence"] = {
        **_evidence(folds_path),
        "rows": len(result.fold_metrics),
    }
    report["prediction_evidence"] = {
        **_evidence(predictions_path),
        "rows": len(result.predictions),
    }
    write_immutable_json(summary_path, report)
    print(
        json.dumps(
            {
                "ok": True,
                "summary": str(summary_path),
                "forward_candidate": report["forward_candidate"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )


def _validate_plan(plan: dict[str, object], features: Path) -> _PlanSettings:
    valid_modes = {
        "hype_entry_l2_model_predeclared_plan_v1",
        "hype_entry_l2_model_predeclared_plan_v2",
        "hype_entry_l2_model_predeclared_plan_v3",
    }
    if plan.get("mode") not in valid_modes:
        raise ValueError("HYPE L2 model plan mode is invalid")
    names = [value.get("name") for value in _object_list(plan.get("candidates"))]
    if names != list(HYPE_ENTRY_L2_MODEL_CANDIDATES):
        raise ValueError("HYPE L2 model plan candidate set differs from code")
    sets = _object(plan.get("feature_sets"), "feature_sets")
    if sets.get("bar_only") != list(HYPE_ENTRY_ATTRIBUTION_FEATURES):
        raise ValueError("HYPE L2 model plan bar features differ from code")
    if sets.get("l2_only") != list(HYPE_ENTRY_L2_FEATURES):
        raise ValueError("HYPE L2 model plan L2 features differ from code")
    _validate_feature_evidence(plan, features)
    walk = _object(plan.get("walk_forward"), "walk_forward")
    target = _object(plan.get("target"), "target")
    return _PlanSettings(
        _positive_int(walk.get("folds"), "folds"),
        _positive_int(walk.get("embargo_minutes"), "embargo_minutes"),
        _positive_float(target.get("modeled_round_trip_bps"), "cost"),
    )


def _validate_feature_evidence(plan: dict[str, object], features: Path) -> None:
    dataset = _object(plan.get("dataset"), "dataset")
    expected = _object(dataset.get("feature_artifact"), "feature_artifact")
    observed = file_evidence(features)
    if expected.get("sha256") != observed["sha256"]:
        raise ValueError("HYPE L2 feature artifact hash differs from frozen plan")


def _validate_materialization(
    materialization: dict[str, object],
    features: Path,
    plan: dict[str, object],
    summary_path: Path,
) -> None:
    contract = _object(materialization.get("contract"), "materialization contract")
    if contract.get("post_entry_fields_excluded_from_model") is not True:
        raise ValueError("HYPE L2 materialization does not prove causal features")
    outputs = _object(materialization.get("output_evidence"), "output_evidence")
    evidence = _object(outputs.get("features"), "feature output evidence")
    if evidence.get("sha256") != file_evidence(features)["sha256"]:
        raise ValueError("HYPE L2 materialization feature hash mismatch")
    dataset = _object(plan.get("dataset"), "dataset")
    planned = dataset.get("materialization_summary")
    if planned is not None:
        expected = _object(planned, "planned materialization")
        if expected.get("sha256") != file_evidence(summary_path)["sha256"]:
            raise ValueError("HYPE L2 materialization hash differs from frozen plan")


def _resolve_plan(plan: dict[str, object]) -> dict[str, object]:
    reference = plan.get("base_plan")
    if reference is None:
        return plan
    identity = _object(reference, "base_plan")
    path_value = identity.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("HYPE L2 base plan path must be non-empty")
    path = Path(path_value)
    if identity.get("sha256") != file_evidence(path)["sha256"]:
        raise ValueError("HYPE L2 base plan hash mismatch")
    base = _read_object(path)
    overrides = _object(plan.get("overrides"), "plan overrides")
    merged = dict(base)
    for key, value in overrides.items():
        current = merged.get(key)
        merged[key] = (
            {**current, **value}
            if isinstance(current, dict) and isinstance(value, dict)
            else value
        )
    merged["mode"] = plan.get("mode")
    merged["schema_version"] = plan.get("schema_version")
    return merged


def _read_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _object(value, str(path))


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"HYPE L2 {label} must be an object")
    return value


def _object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("HYPE L2 candidates must be an object list")
    return value


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"HYPE L2 plan {label} must be positive")
    return value


def _positive_float(value: object, label: str) -> float:
    if not isinstance(value, int | float) or value <= 0.0:
        raise ValueError(f"HYPE L2 plan {label} must be positive")
    return float(value)


def _evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"HYPE L2 model input does not exist: {path}")


def _require_absent(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"immutable HYPE L2 model output exists: {path}")


if __name__ == "__main__":
    main()
