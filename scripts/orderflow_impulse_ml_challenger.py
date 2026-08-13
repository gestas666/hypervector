#!/usr/bin/env python3
"""Run fixed Ridge/LightGBM annotations on the 1m impulse event sidecar."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from numbers import Integral, Real
from pathlib import Path
from typing import Sequence

import pandas as pd

from hypervector.research.orderflow_impulse_ml import (
    evaluate_orderflow_impulse_models,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Evaluate annotation models and publish immutable OOS evidence."""
    args = _parser().parse_args(argv)
    source_report = Path(args.source_report)
    output = Path(args.out)
    predictions_path = output.with_name(f"{output.stem}.predictions.parquet")
    selected_path = output.with_name(f"{output.stem}.selected.parquet")
    _ensure_available(output, predictions_path, selected_path)
    source = _source_contract(source_report)
    sidecar = Path(str(source["sidecar"]["path"]))
    _verify_sha256(sidecar, str(source["sidecar"]["sha256"]))
    outcomes = pd.read_parquet(sidecar)
    result = evaluate_orderflow_impulse_models(outcomes)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.predictions.to_parquet(predictions_path, index=False)
    result.selected.to_parquet(selected_path, index=False)
    report = {
        "schema_version": "orderflow_impulse_ml_challenger_v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "place_attempted": False,
        "source_report": str(source_report),
        "source_report_sha256": _file_sha256(source_report),
        "source_sidecar": str(sidecar),
        "source_sidecar_sha256": _file_sha256(sidecar),
        "model_contract": {
            "candidates": ["ridge_net_return", "lightgbm_net_return"],
            "target": "net_return_bps_nominal",
            "folds": 3,
            "embargo_minutes": 15,
            "selection": "fold_training_prediction_80th_percentile_then_best_side",
            "one_position_per_symbol": True,
        },
        "metrics": result.metrics,
        "fold_metrics": _records(result.fold_metrics),
        "row_counts": {
            "source_outcomes": len(outcomes),
            "oos_predictions": len(result.predictions),
            "selected_candidates": len(result.selected),
            "accepted_selected": int(result.selected["accepted"].sum()),
        },
        "predictions": _sidecar_record(predictions_path, result.predictions),
        "selected": _sidecar_record(selected_path, result.selected),
        "decision_policy": {
            "automatic_promotion": False,
            "requires_positive_ic_all_folds": True,
            "requires_positive_selected_net": True,
            "requires_positive_net_ex_largest_winner": True,
            "requires_future_prospective_repeat": True,
        },
    }
    output.write_text(
        json.dumps(_json_safe(report), indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote report-only order-flow ML artifact: {output}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def _source_contract(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"source order-flow report does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "orderflow_impulse_development_v1":
        raise ValueError("source report schema is not the deterministic v1 contract")
    if payload.get("execution_authority") != "none":
        raise ValueError("source report unexpectedly carries execution authority")
    return payload


def _sidecar_record(path: Path, rows: pd.DataFrame) -> dict[str, object]:
    return {"path": str(path), "sha256": _file_sha256(path), "rows": len(rows)}


def _verify_sha256(path: Path, expected: str) -> None:
    observed = _file_sha256(path)
    if observed != expected:
        raise ValueError(
            f"source sidecar hash mismatch: expected {expected}, observed {observed}"
        )


def _ensure_available(*paths: Path) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(f"order-flow ML outputs already exist: {existing}")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (datetime, pd.Timestamp)):
        return pd.Timestamp(value).isoformat()
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
