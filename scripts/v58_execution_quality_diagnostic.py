#!/usr/bin/env python3
"""Publish an immutable report-only V58 execution-quality diagnosis."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import sys

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_development_provenance import require_unchanged_file
from hypervector.research.v58_execution_quality_diagnostic import (
    build_v58_execution_quality_diagnostic,
)

_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable report-only publisher parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def publish_report(args: argparse.Namespace) -> dict[str, object]:
    """Build and immutably publish one source-bound diagnostic."""
    checkpoint_evidence = _path_evidence(args.checkpoint)
    generators = _generator_identity()
    payload = _load_object(args.checkpoint)
    report = build_v58_execution_quality_diagnostic(payload)
    require_unchanged_file(args.checkpoint, checkpoint_evidence)
    _require_unchanged_generators(generators)
    report["source_evidence"] = {"checkpoint": checkpoint_evidence}
    report["source_checkpoint_snapshot"] = dict(payload)
    report["generator_identity"] = generators
    write_immutable_json(args.out, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Run the immutable report-only publisher."""
    args = build_parser().parse_args(argv)
    try:
        report = publish_report(args)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"V58 execution-quality diagnostic failed: {exc}", file=sys.stderr)
        return 2
    output = {
        "out": str(args.out),
        "mode": report.get("mode"),
        "execution_authority": report.get("contract", {}).get("execution_authority"),
        "primary_attribution": report.get("diagnosis", {}).get("primary_attribution"),
    }
    print(json.dumps(output, sort_keys=True))
    return 0


def _load_object(path: Path) -> Mapping[str, object]:
    payload: object = json.loads(path.read_bytes())
    if not isinstance(payload, Mapping):
        raise ValueError("V58 execution diagnostic checkpoint must be an object")
    return payload


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _generator_identity() -> list[dict[str, object]]:
    return [_path_evidence(path) for path in _generator_paths()]


def _require_unchanged_generators(expected: list[dict[str, object]]) -> None:
    for row in expected:
        require_unchanged_file(Path(str(row["path"])), row)


def _generator_paths() -> tuple[Path, ...]:
    project = Path(__file__).resolve().parents[1]
    return (
        Path(__file__).resolve(),
        project / "src/hypervector/research/v58_execution_quality_diagnostic.py",
        project / "src/hypervector/data/oxa_storage.py",
        project / "src/hypervector/research/hip3_development_provenance.py",
        project / "pyproject.toml",
        project / "uv.lock",
    )


if __name__ == "__main__":
    raise SystemExit(main())
