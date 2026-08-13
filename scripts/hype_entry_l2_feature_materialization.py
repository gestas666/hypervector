#!/usr/bin/env python3
"""Publish immutable causal HYPE entry L2 features and coverage evidence."""

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
from hypervector.research.hype_entry_l2_features import (
    HypeL2EntryDataset,
    build_hype_entry_l2_dataset,
)

_DEFAULT_FEATURES = Path(
    "data/logs/research/"
    "hype_breakout_entry_attribution_development_v2_20260804.features.parquet"
)
_DEFAULT_AUDIT_INDEX = Path(
    "data/logs/research/hype_breakout_l2_signal_windows_audit_v1/index.parquet"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable causal L2 feature command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=_DEFAULT_FEATURES)
    parser.add_argument("--audit-index", type=Path, default=_DEFAULT_AUDIT_INDEX)
    parser.add_argument("--sampling-interval-ms", type=int)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def output_paths(out: Path) -> tuple[Path, Path, Path]:
    """Return summary, covered-feature, and full-coverage paths."""
    if out.suffix != ".json":
        raise ValueError("HYPE L2 feature output must use .json")
    return (
        out,
        out.with_suffix(".features.parquet"),
        out.with_suffix(".coverage.parquet"),
    )


def run(args: argparse.Namespace) -> HypeL2EntryDataset:
    """Build causal features from frozen source and audited L2 evidence."""
    _require_file(args.features, "HYPE development features")
    _require_file(args.audit_index, "HYPE L2 audit index")
    raw = pd.read_parquet(args.features)
    audit = pd.read_parquet(args.audit_index)
    return build_hype_entry_l2_dataset(
        raw,
        audit,
        sampling_interval_ms=args.sampling_interval_ms,
    )


def main() -> None:
    """Write immutable sidecars first and their hash-linked report last."""
    args = build_parser().parse_args()
    summary_path, feature_path, coverage_path = output_paths(args.out)
    for path in (summary_path, feature_path, coverage_path):
        _require_absent(path)
    result = run(args)
    write_immutable_parquet(feature_path, result.rows)
    write_immutable_parquet(coverage_path, result.coverage)
    report = dict(result.report)
    report["source_evidence"] = {
        "features": _evidence(args.features, len(result.coverage)),
        "audit_index": _evidence(args.audit_index, len(result.coverage)),
    }
    report["output_evidence"] = {
        "features": _evidence(feature_path, len(result.rows)),
        "coverage": _evidence(coverage_path, len(result.coverage)),
    }
    write_immutable_json(summary_path, report)
    print(
        json.dumps(
            {
                "ok": True,
                "summary": str(summary_path),
                "features": str(feature_path),
                "coverage": str(coverage_path),
                "covered_rows": len(result.rows),
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )


def _evidence(path: Path, rows: int) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path), "rows": rows}


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} do not exist: {path}")


def _require_absent(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"immutable HYPE L2 feature output exists: {path}")


if __name__ == "__main__":
    main()
