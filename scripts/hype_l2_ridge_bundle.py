"""Freeze the cadence-parity HYPE L2 Ridge observer as deterministic JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, cast

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.ml.hype_l2_ridge_bundle import fit_hype_l2_ridge_bundle

_ROOT = Path("data/logs/research")
_DEFAULT_FEATURES = _ROOT / (
    "hype_breakout_entry_l2_features_live_cadence1000_v3_20260806.features.parquet"
)
_DEFAULT_DEVELOPMENT_REPORT = (
    _ROOT / "hype_breakout_entry_l2_model_live_cadence_v3_20260806.json"
)
_DEFAULT_MODEL_PLAN = (
    _ROOT / "hype_breakout_entry_l2_model_live_cadence_plan_v3_20260806.json"
)
_DEFAULT_MATERIALIZATION = _ROOT / (
    "hype_breakout_entry_l2_features_live_cadence1000_v3_20260806.json"
)
_DEFAULT_BUNDLE_PLAN = _ROOT / "hype_l2_ridge_observe_bundle_plan_v1_20260806.json"
_DEFAULT_OUTPUT = Path("data/models/hype_l2_ridge_observe_v1.json")


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded, offline, no-submit bundle command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=_DEFAULT_FEATURES)
    parser.add_argument(
        "--development-report", type=Path, default=_DEFAULT_DEVELOPMENT_REPORT
    )
    parser.add_argument("--model-plan", type=Path, default=_DEFAULT_MODEL_PLAN)
    parser.add_argument(
        "--materialization-summary", type=Path, default=_DEFAULT_MATERIALIZATION
    )
    parser.add_argument("--bundle-plan-out", type=Path, default=_DEFAULT_BUNDLE_PLAN)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUTPUT)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Validate frozen evidence, fit one model, and publish immutable artifacts."""
    sources = _source_evidence(args)
    report = _json_object(args.development_report)
    model_plan = _json_object(args.model_plan)
    materialization = _json_object(args.materialization_summary)
    _validate_sources(report, model_plan, materialization)
    plan = _bundle_plan(args, sources)
    _ensure_immutable_json(args.bundle_plan_out, plan)
    rows = pd.read_parquet(args.features)
    evidence = {
        "feature_artifact_sha256": _sha(sources, "features"),
        "model_plan_sha256": _sha(sources, "model_plan"),
        "development_report_sha256": _sha(sources, "development_report"),
    }
    bundle = fit_hype_l2_ridge_bundle(rows, evidence=evidence)
    _ensure_immutable_json(args.out, bundle.to_payload())
    return {
        "ok": True,
        "execution_authority": "none",
        "training_rows": len(rows),
        "bundle_plan": file_evidence(args.bundle_plan_out),
        "bundle": file_evidence(args.out),
    }


def _source_evidence(args: argparse.Namespace) -> dict[str, dict[str, object]]:
    paths = {
        "features": args.features,
        "development_report": args.development_report,
        "model_plan": args.model_plan,
        "materialization_summary": args.materialization_summary,
    }
    for label, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"HYPE L2 bundle {label} is missing: {path}")
    return {
        label: {"path": str(path.resolve()), **file_evidence(path)}
        for label, path in paths.items()
    }


def _validate_sources(
    report: Mapping[str, object],
    model_plan: Mapping[str, object],
    materialization: Mapping[str, object],
) -> None:
    candidate = _mapping(report.get("forward_candidate"), "forward_candidate")
    candidates = _mapping(report.get("candidates"), "candidates")
    ridge = _mapping(candidates.get("l2_ridge_return"), "l2_ridge_return")
    if report.get("mode") != "hype_entry_l2_return_model_development_v1":
        raise ValueError("HYPE L2 development report mode is invalid")
    if candidate.get("candidate") != "l2_ridge_return":
        raise ValueError("HYPE L2 forward candidate is not Ridge")
    if ridge.get("development_supported") is not True:
        raise ValueError("HYPE L2 Ridge is not development-supported")
    _require_no_authority(_mapping(report.get("contract"), "report contract"))
    if model_plan.get("mode") != "hype_entry_l2_model_predeclared_plan_v3":
        raise ValueError("HYPE L2 model plan mode is invalid")
    overrides = _mapping(model_plan.get("overrides"), "model plan overrides")
    parity = _mapping(overrides.get("implementation_parity"), "implementation parity")
    if parity.get("sampling_interval_ms") != 1_000:
        raise ValueError("HYPE L2 model plan cadence is not one second")
    if materialization.get("mode") != "hype_entry_l2_features_development_v1":
        raise ValueError("HYPE L2 materialization mode is invalid")
    sampling = _mapping(materialization.get("sampling"), "sampling")
    if sampling.get("interval_ms") != 1_000:
        raise ValueError("HYPE L2 materialization cadence is not one second")
    _require_no_authority(
        _mapping(materialization.get("contract"), "materialization contract")
    )


def _require_no_authority(contract: Mapping[str, object]) -> None:
    if contract.get("execution_authority") != "none":
        raise ValueError("HYPE L2 evidence has execution authority")


def _bundle_plan(
    args: argparse.Namespace,
    sources: Mapping[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "hype_l2_ridge_observe_bundle_plan_v1",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
            "automatic_promotion": False,
        },
        "model": {
            "family": "standard_scaler_ridge_regression",
            "alpha": 10.0,
            "sampling_interval_ms": 1_000,
            "training_target": "gross_return_bps",
            "hyperparameter_sweeps": 0,
        },
        "sources": dict(sources),
        "output": str(args.out.resolve()),
    }


def _ensure_immutable_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        observed = json.loads(path.read_text(encoding="utf-8"))
        if observed != payload:
            raise ValueError(f"existing immutable HYPE L2 artifact differs: {path}")
        return
    write_immutable_json(path, payload)


def _sha(sources: Mapping[str, dict[str, object]], label: str) -> str:
    value = sources[label].get("sha256")
    if not isinstance(value, str):
        raise ValueError(f"HYPE L2 source {label} has no SHA-256")
    return value


def _json_object(path: Path) -> Mapping[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    return _mapping(value, str(path))


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"HYPE L2 {label} must be an object")
    return cast(dict[str, object], value)


def main() -> int:
    """Freeze the exact observer bundle and print secret-free evidence."""
    result = run(build_parser().parse_args())
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
