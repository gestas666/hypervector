"""Score frozen Hypervelocity challengers on one untouched source replay."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
)
from hypervector.ml.hypervelocity_challenger_holdout import (
    FrozenHoldoutResult,
    score_frozen_challengers,
)
from hypervector.ml.hypervelocity_metric_io import json_safe_metrics as _json_metrics
from hypervector.research.hypervelocity_metalabel_report import (
    MetalabelDatasetAssembly,
)
from hypervector.research.hypervelocity_metalabel_shape import population_summary
from hypervector.research.hypervelocity_source_metalabel import (
    assemble_source_metalabel_dataset,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
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
        raise FileExistsError(f"holdout output already exists: {existing[0]}")


def _report(
    *,
    assembly: MetalabelDatasetAssembly,
    result: FrozenHoldoutResult,
    artifacts: dict[str, Path],
) -> dict[str, object]:
    rows = assembly.rows
    metrics = _json_metrics(result.metrics)
    selected = min(
        metrics, key=lambda name: float(metrics[name]["log_loss"] or math.inf)
    )
    return {
        "ok": True,
        "report_only": True,
        "runtime_strategy_changed": False,
        "scoring_retrained_models": False,
        "selection_is_promotion": False,
        "selected_by_holdout_log_loss": selected,
        "population": population_summary(rows, "liquidation_risk"),
        "metrics": metrics,
        "feature_coverage": assembly.feature_coverage,
        "training_evidence": result.evidence,
        "holdout_source_evidence": assembly.source_evidence,
        "holdout_archive_evidence": assembly.archive_evidence,
        "runtime_policy": assembly.runtime_policy,
        "data_evidence": {
            name: file_evidence(path) for name, path in artifacts.items()
        },
        "limitations": [
            "This is one later holdout block, not repeated forward confirmation.",
            "L2 MBP cannot reveal private queue position or hidden liquidity.",
            "No scored model may filter, size, or execute trades.",
        ],
    }


def main() -> int:
    """Build holdout features and score exact frozen models without fitting."""
    args = _parser().parse_args()
    artifacts = _artifact_paths(args.out)
    try:
        _ensure_new([args.out, *artifacts.values()])
        assembly = assemble_source_metalabel_dataset(
            replay_paths=[args.replay],
            bars_path=args.bars,
            config_path=args.config,
            data_root=args.data_root,
            expected_resolved=args.expected_resolved,
            expected_liquidations=args.expected_liquidations,
        )
        result = score_frozen_challengers(
            assembly.rows,
            training_report_path=args.training_report,
            training_dataset_path=args.training_dataset,
            model_dir=args.model_dir,
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        assembly.rows.to_parquet(artifacts["dataset"], index=False)
        result.predictions.to_parquet(artifacts["predictions"], index=False)
        report = _report(assembly=assembly, result=result, artifacts=artifacts)
        write_immutable_json(args.out, report)
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "selected_by_holdout_log_loss": report["selected_by_holdout_log_loss"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
