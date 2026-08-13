"""Score frozen source-state challengers on one later gap-free replay block."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.ml.hypervelocity_metric_io import json_safe_metrics
from hypervector.ml.hypervelocity_source_challenger_holdout import (
    score_frozen_source_challengers,
    source_candidate_acceptance,
)
from hypervector.research.hypervelocity_metalabel_report import (
    MetalabelDatasetAssembly,
)
from hypervector.research.hypervelocity_metalabel_shape import population_summary
from hypervector.research.hypervelocity_source_metalabel import (
    assemble_source_metalabel_dataset,
)

_DEVELOPMENT_END = pd.Timestamp("2026-01-09T00:00:00Z")
_MIN_RESOLVED = 50
_MIN_LIQUIDATIONS = 10


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--strict-labels", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--expected-resolved", type=int, required=True)
    parser.add_argument("--expected-liquidations", type=int, required=True)
    parser.add_argument("--training-report", type=Path, required=True)
    parser.add_argument("--training-dataset", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _artifact_paths(out: Path) -> dict[str, Path]:
    stem = out.with_suffix("")
    return {
        "dataset": Path(f"{stem}_dataset.parquet"),
        "predictions": Path(f"{stem}_predictions.parquet"),
    }


def _ensure_new(paths: list[Path]) -> None:
    existing = [path for path in paths if path.exists()]
    if existing:
        raise FileExistsError(f"source-state holdout output exists: {existing[0]}")


def _validate_holdout_population(rows: pd.DataFrame) -> dict[str, int]:
    resolved = len(rows)
    liquidations = int(rows["liquidation_risk"].astype(int).sum())
    if resolved < _MIN_RESOLVED or liquidations < _MIN_LIQUIDATIONS:
        raise ValueError(
            "source-state holdout requires at least 50 resolved and 10 liquidations; "
            f"observed {resolved} resolved and {liquidations} liquidations"
        )
    return {"resolved": resolved, "liquidations": liquidations}


def _validate_holdout_time(rows: pd.DataFrame) -> None:
    first = pd.to_datetime(int(rows["signal_ts_ms"].min()), unit="ms", utc=True)
    if first < _DEVELOPMENT_END:
        raise ValueError(
            f"source-state holdout begins before frozen development end: {first}"
        )


def _report(
    assembly: MetalabelDatasetAssembly,
    metrics: dict[str, dict[str, float | int | None]],
    evidence: dict[str, object],
    artifacts: dict[str, Path],
) -> dict[str, object]:
    acceptance = source_candidate_acceptance(metrics)
    selected = min(
        metrics,
        key=lambda name: float(metrics[name]["log_loss"] or math.inf),
    )
    return {
        "ok": True,
        "report_only": True,
        "runtime_strategy_changed": False,
        "scoring_retrained_models": False,
        "selection_is_promotion": False,
        "selected_by_holdout_log_loss": selected,
        "passing_source_candidates": [
            name for name, checks in acceptance.items() if checks["passed"]
        ],
        "acceptance": acceptance,
        "population": population_summary(assembly.rows, "liquidation_risk"),
        "metrics": metrics,
        "feature_coverage": assembly.feature_coverage,
        "training_evidence": evidence,
        "holdout_source_evidence": assembly.source_evidence,
        "holdout_archive_evidence": assembly.archive_evidence,
        "runtime_policy": assembly.runtime_policy,
        "data_evidence": {
            name: file_evidence(path) for name, path in artifacts.items()
        },
        "predeclared_plan": file_evidence(
            Path("docs/plans/2026-07-29-hypervelocity-source-state-challenger.md")
        ),
        "holdout_contamination": (
            "Two April losing rows were inspected qualitatively after model freeze; "
            "no model, threshold, or acceptance criterion changed before scoring."
        ),
        "limitations": [
            "This delayed holdout is not fully untouched because two loss rows were inspected.",
            "Public L2 cannot reveal private queue position or hidden liquidity.",
            "No scored model may filter, size, or execute trades.",
        ],
    }


def _run(args: argparse.Namespace) -> dict[str, object]:
    assembly = assemble_source_metalabel_dataset(
        replay_paths=[args.replay],
        bars_path=args.bars,
        config_path=args.config,
        data_root=args.data_root,
        expected_resolved=args.expected_resolved,
        expected_liquidations=args.expected_liquidations,
        source_labels_path=args.strict_labels,
    )
    _validate_holdout_population(assembly.rows)
    _validate_holdout_time(assembly.rows)
    result = score_frozen_source_challengers(
        assembly.rows,
        training_report_path=args.training_report,
        training_dataset_path=args.training_dataset,
        model_dir=args.model_dir,
    )
    artifacts = _artifact_paths(args.out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    assembly.rows.to_parquet(artifacts["dataset"], index=False)
    result.predictions.to_parquet(artifacts["predictions"], index=False)
    metrics = json_safe_metrics(result.metrics)
    report = _report(assembly, metrics, result.evidence, artifacts)
    write_immutable_json(args.out, report)
    return report


def main() -> int:
    """Score one verified later block without modifying frozen models."""
    args = _parser().parse_args()
    artifacts = _artifact_paths(args.out)
    try:
        _ensure_new([args.out, *artifacts.values()])
        report = _run(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "passing_source_candidates": report["passing_source_candidates"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
