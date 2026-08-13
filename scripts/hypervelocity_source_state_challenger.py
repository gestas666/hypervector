"""Train the predeclared observe-only Hypervelocity source-state challengers."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.ml.hypervelocity_metric_io import json_safe_metrics
from hypervector.ml.hypervelocity_source_challenger import (
    SOURCE_CANDIDATE_NAMES,
    train_source_state_challengers,
)
from hypervector.research.hypervelocity_metalabel_shape import population_summary
from hypervector.research.hypervelocity_source_metalabel import (
    assemble_source_metalabel_dataset,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, action="append", required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--strict-labels", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--expected-resolved", type=int, required=True)
    parser.add_argument("--expected-liquidations", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--embargo-minutes", type=int, default=60)
    return parser


def _artifact_paths(out: Path) -> dict[str, Path]:
    stem = out.with_suffix("")
    return {
        "dataset": Path(f"{stem}_dataset.parquet"),
        "predictions": Path(f"{stem}_predictions.parquet"),
        "fold_metrics": Path(f"{stem}_fold_metrics.parquet"),
    }


def _ensure_new(paths: list[Path]) -> None:
    existing = [path for path in paths if path.exists()]
    if existing:
        raise FileExistsError(f"source challenger output already exists: {existing[0]}")


def main() -> int:
    """Assemble development evidence and persist uninstalled source models."""
    args = _parser().parse_args()
    artifacts = _artifact_paths(args.out)
    try:
        _ensure_new([args.out, args.model_dir, *artifacts.values()])
        assembly = assemble_source_metalabel_dataset(
            replay_paths=args.replay,
            bars_path=args.bars,
            config_path=args.config,
            data_root=args.data_root,
            expected_resolved=args.expected_resolved,
            expected_liquidations=args.expected_liquidations,
            source_labels_path=args.strict_labels,
        )
        result = train_source_state_challengers(
            assembly.rows,
            args.model_dir,
            n_splits=args.n_splits,
            embargo_minutes=args.embargo_minutes,
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        assembly.rows.to_parquet(artifacts["dataset"], index=False)
        result.predictions.to_parquet(artifacts["predictions"], index=False)
        result.fold_metrics.to_parquet(artifacts["fold_metrics"], index=False)
        metrics = json_safe_metrics(result.metrics)
        selected = min(
            SOURCE_CANDIDATE_NAMES,
            key=lambda name: float(metrics[name]["log_loss_mean"] or math.inf),
        )
        report = {
            "ok": True,
            "report_only": True,
            "runtime_strategy_changed": False,
            "selection_is_promotion": False,
            "development_end_utc": "2026-01-09T00:00:00+00:00",
            "forward_holdout_start_utc": "2026-01-09T00:00:00+00:00",
            "selected_by_development_log_loss": selected,
            "searched_set": list(SOURCE_CANDIDATE_NAMES),
            "population": population_summary(assembly.rows, "liquidation_risk"),
            "metrics": metrics,
            "feature_coverage": assembly.feature_coverage,
            "runtime_policy": assembly.runtime_policy,
            "source_evidence": assembly.source_evidence,
            "archive_evidence": assembly.archive_evidence,
            "model_evidence": {
                **{
                    name: file_evidence(path)
                    for name, path in result.model_paths.items()
                },
                "metadata": file_evidence(result.metadata_path),
            },
            "data_evidence": {
                name: file_evidence(path) for name, path in artifacts.items()
            },
            "predeclared_plan": file_evidence(
                Path("docs/plans/2026-07-29-hypervelocity-source-state-challenger.md")
            ),
            "limitations": [
                "Source-state features were selected after inspecting pre-Jan 9 outcomes.",
                "All metrics in this report are development evidence only.",
                "No model may filter, scale, or execute runtime trades.",
            ],
        }
        write_immutable_json(args.out, report)
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "selected_by_development_log_loss": selected,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
