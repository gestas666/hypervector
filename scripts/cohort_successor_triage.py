#!/usr/bin/env python3
"""Publish immutable, report-only cohort successor triage."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import tempfile

from hypervector.research.cohort_successor_triage import build_successor_triage


def build_parser() -> argparse.ArgumentParser:
    """Build the successor-triage command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the successor-triage command."""
    args = build_parser().parse_args(argv)
    source = args.audit.resolve()
    output = args.out.resolve()
    content = source.read_bytes()
    audit = _mapping(json.loads(content), "cohort audit")
    report = {
        **build_successor_triage(audit),
        "evidence": {
            "audit_path": str(source),
            "audit_sha256": hashlib.sha256(content).hexdigest(),
            "audit_bytes": len(content),
        },
    }
    _write_exclusive(output, report)
    print(
        json.dumps(
            {"ok": True, "output": str(output), "summary": report["summary"]},
            sort_keys=True,
        )
    )
    return 0


def _write_exclusive(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
