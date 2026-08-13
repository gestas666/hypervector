#!/usr/bin/env python3
"""Publish one immutable execution cash-drag diagnostic from a checkpoint."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

from hypervector.research.cohort_execution_drag_diagnostic import (
    build_execution_drag_diagnostic,
)

Record = Mapping[str, object]

_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_GENERATOR_FILES = (
    Path(__file__).resolve(),
    Path("src/hypervector/research/cohort_execution_drag_diagnostic.py").resolve(),
    Path("src/hypervector/research/cohort_trade_performance.py").resolve(),
)


def build_parser() -> argparse.ArgumentParser:
    """Build explicit checkpoint and immutable output arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Build a source-bound diagnostic without changing runtime state."""
    if args.checkpoint.resolve() == args.out.resolve():
        raise ValueError("execution-drag output must differ from its checkpoint")
    raw = args.checkpoint.read_bytes()
    checkpoint = _mapping(json.loads(raw), "checkpoint")
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    reflections = _mapping(audit.get("trade_reflections"), "trade reflections")
    trades = reflections.get("trades")
    if not isinstance(trades, list):
        raise ValueError("trade reflections must contain a trades list")
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "evidence": {"checkpoint": _byte_record(args.checkpoint, raw)},
        "generator_identity": {"files": _generator_identity()},
        "diagnostic": build_execution_drag_diagnostic(trades),
    }


def write_immutable_report(path: Path, report: Record) -> None:
    """Publish a complete JSON artifact without replacing prior evidence."""
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, destination)
    except FileExistsError as exc:
        raise FileExistsError(
            f"execution-drag diagnostic already exists: {path}"
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _require_unchanged_source(args: argparse.Namespace, report: Record) -> None:
    evidence = _mapping(report.get("evidence"), "diagnostic evidence")
    expected = _mapping(evidence.get("checkpoint"), "checkpoint evidence")
    if expected != _file_record(args.checkpoint):
        raise RuntimeError("checkpoint changed during execution-drag diagnostic")
    generator = _mapping(report.get("generator_identity"), "generator identity")
    if generator.get("files") != _generator_identity():
        raise RuntimeError("execution-drag diagnostic generator changed")


def _generator_identity() -> list[dict[str, object]]:
    return [_file_record(path) for path in _GENERATOR_FILES]


def _file_record(path: Path) -> dict[str, object]:
    return _byte_record(path, path.read_bytes())


def _byte_record(path: Path, raw: bytes) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Build, revalidate, and publish the immutable diagnostic."""
    args = build_parser().parse_args(argv)
    report = run_report(args)
    _require_unchanged_source(args, report)
    write_immutable_report(args.out, report)
    print(json.dumps({"state": "published", "output": str(args.out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
