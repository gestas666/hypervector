#!/usr/bin/env python3
"""Publish an immutable delta between two v30 forward-readiness reports."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from pathlib import Path
import sys

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.v30_forward_delta import build_v30_forward_delta


Record = Mapping[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only v30 delta command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def publish(args: argparse.Namespace) -> tuple[dict[str, object], Path]:
    """Load, compare, and immutably publish two source-bound reports."""
    output = _path(args.out, "output")
    if output.exists():
        raise FileExistsError(f"immutable v30 delta output exists: {output}")
    before, before_evidence = _load(_path(args.before, "before report"))
    after, after_evidence = _load(_path(args.after, "after report"))
    report = build_v30_forward_delta(before, after)
    report["source_evidence"] = {
        "before": before_evidence,
        "after": after_evidence,
    }
    write_immutable_json(output, report)
    return report, output


def _load(path: Path) -> tuple[Record, dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(f"v30 readiness report is missing: {path}")
    raw = path.read_bytes()
    parsed = json.loads(raw)
    if not isinstance(parsed, Mapping):
        raise TypeError(f"v30 readiness report must contain an object: {path}")
    return parsed, {
        "path": str(path),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _path(value: object, label: str) -> Path:
    if not isinstance(value, Path):
        raise TypeError(f"{label} must be a path")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Publish one delta and print its bounded change classification."""
    try:
        report, output = publish(build_parser().parse_args(argv))
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        print(f"v30 forward delta refused: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(output),
                "summary": report["summary"],
                "assessment": report["assessment"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
