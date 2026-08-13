#!/usr/bin/env python3
"""Evaluate two report-only HYPE entry models on frozen development evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
    write_immutable_parquet,
)
from hypervector.ml.hype_entry_challenger import (
    HypeEntryChallengerResult,
    evaluate_hype_entry_challengers,
)

_DEFAULT_FEATURES = Path(
    "data/logs/research/"
    "hype_breakout_entry_attribution_development_v2_20260804.features.parquet"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable development-only entry-model command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=_DEFAULT_FEATURES)
    parser.add_argument("--fold-count", type=int, default=5)
    parser.add_argument("--embargo-minutes", type=int, default=60)
    parser.add_argument("--modeled-round-trip-bps", type=float, default=13.0)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def output_paths(out: Path) -> tuple[Path, Path, Path]:
    """Return the summary, fold-metric, and OOS-prediction paths."""
    if out.suffix != ".json":
        raise ValueError("HYPE entry-model output must use .json")
    return (
        out,
        out.with_suffix(".folds.parquet"),
        out.with_suffix(".predictions.parquet"),
    )


def run(args: argparse.Namespace) -> HypeEntryChallengerResult:
    """Read the frozen feature artifact and evaluate without fitting runtime state."""
    if not args.features.is_file():
        raise FileNotFoundError(
            f"HYPE development features do not exist: {args.features}"
        )
    rows = pd.read_parquet(args.features)
    return evaluate_hype_entry_challengers(
        rows,
        n_splits=args.fold_count,
        embargo_minutes=args.embargo_minutes,
        modeled_round_trip_bps=args.modeled_round_trip_bps,
    )


def main() -> None:
    """Publish immutable OOS sidecars first and their hash-linked report last."""
    args = build_parser().parse_args()
    summary_path, folds_path, predictions_path = output_paths(args.out)
    for path in (summary_path, folds_path, predictions_path):
        _require_absent(path)
    result = run(args)
    write_immutable_parquet(folds_path, result.fold_metrics)
    write_immutable_parquet(predictions_path, result.predictions)
    report = dict(result.report)
    report["data_evidence"] = {
        "features_path": str(args.features.resolve()),
        "features": file_evidence(args.features),
        "feature_rows": len(result.rows),
    }
    report["fold_evidence"] = _sidecar_evidence(folds_path, len(result.fold_metrics))
    report["prediction_evidence"] = _sidecar_evidence(
        predictions_path,
        len(result.predictions),
    )
    write_immutable_json(summary_path, report)
    print(
        json.dumps(
            {
                "ok": True,
                "summary": str(summary_path),
                "folds": str(folds_path),
                "predictions": str(predictions_path),
                "forward_candidate": report["forward_candidate"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )


def _sidecar_evidence(path: Path, rows: int) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path), "rows": rows}


def _require_absent(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"immutable HYPE entry-model output exists: {path}")


if __name__ == "__main__":
    main()
