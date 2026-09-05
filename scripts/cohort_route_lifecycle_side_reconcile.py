#!/usr/bin/env python3
"""Publish side-aware reconciliation for one route lifecycle watcher."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from pathlib import Path

from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.cohort_route_lifecycle_side_reconciliation import (
    reconcile_route_lifecycle_sides,
)

Record = Mapping[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only side reconciliation parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run_command(
    status_path: Path, checkpoint_path: Path, out: Path
) -> dict[str, object]:
    """Reconcile one exact snapshot and atomically publish source-bound evidence."""
    status, status_evidence = _read_json(status_path, "route lifecycle status")
    checkpoint, checkpoint_evidence = _read_json(checkpoint_path, "checkpoint")
    report = reconcile_route_lifecycle_sides(status, checkpoint)
    report["source_evidence"] = {
        "status": status_evidence,
        "checkpoint": checkpoint_evidence,
    }
    _require_unchanged(status_path, status_evidence, "route lifecycle status")
    _require_unchanged(checkpoint_path, checkpoint_evidence, "checkpoint")
    write_atomic_json(out, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Run one execution-incapable side reconciliation."""
    args = build_parser().parse_args(argv)
    run_command(args.status, args.checkpoint, args.out)
    return 0


def _read_json(path: Path, label: str) -> tuple[Record, dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must contain a JSON object")
    return payload, _evidence(path, raw)


def _require_unchanged(path: Path, expected: Record, label: str) -> None:
    raw = path.read_bytes()
    if _evidence(path, raw) != dict(expected):
        raise ValueError(f"{label} changed during side reconciliation")


def _evidence(path: Path, raw: bytes) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "bytes": len(raw),
        "sha256": sha256(raw).hexdigest(),
    }


if __name__ == "__main__":
    raise SystemExit(main())
