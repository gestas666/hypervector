#!/usr/bin/env python3
"""Freeze one immutable report-only v30 live-forward readiness prefix."""

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

from hypervector.research.v30_forward_readiness import (
    build_v30_forward_readiness,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Load one checkpoint snapshot and publish a source-bound readiness report."""
    args = _parser().parse_args(argv)
    output = Path(args.out)
    if output.exists():
        raise FileExistsError(f"v30 readiness output already exists: {output}")
    checkpoint_path = Path(args.checkpoint)
    checkpoint_bytes = checkpoint_path.read_bytes()
    checkpoint = json.loads(checkpoint_bytes)
    if not isinstance(checkpoint, dict):
        raise ValueError("v30 readiness checkpoint root must be a mapping")
    decisions_path = Path(args.decisions)
    prefix_bytes = decisions_path.stat().st_size
    report = build_v30_forward_readiness(checkpoint, Path(args.config))
    artifact = {
        **report,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_identity": {
            "checkpoint_path": str(checkpoint_path),
            "checkpoint_bytes": len(checkpoint_bytes),
            "checkpoint_sha256": sha256(checkpoint_bytes).hexdigest(),
            "decisions_path": str(decisions_path),
            "decisions_prefix_bytes": prefix_bytes,
            "decisions_prefix_sha256": _prefix_sha256(decisions_path, prefix_bytes),
            "candidate_path": str(args.config),
            "candidate_sha256": _file_sha256(Path(args.config)),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(_json_safe(artifact), indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote report-only v30 forward-readiness artifact: {output}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--decisions", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def _prefix_sha256(path: Path, byte_count: int) -> str:
    if byte_count < 0:
        raise ValueError("decisions prefix byte count cannot be negative")
    digest = sha256()
    remaining = byte_count
    with path.open("rb") as handle:
        while remaining:
            chunk = handle.read(min(1024 * 1024, remaining))
            if not chunk:
                raise OSError("decisions ledger became shorter during prefix hash")
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
