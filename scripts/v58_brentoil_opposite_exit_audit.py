#!/usr/bin/env python3
"""Publish an immutable, authority-none V58 BRENTOIL opposite-exit audit."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
from typing import cast

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.v58_brentoil_opposite_exit_audit import (
    build_v58_brentoil_opposite_exit_audit,
)


Record = dict[str, object]
_ROOT = Path(__file__).resolve().parents[1]
_STRATEGY_NEEDLE = (
    b'"strategy_id":"hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"'
)


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--decision-ledger", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def publish_report(args: argparse.Namespace) -> Record:
    """Freeze exact inputs and publish one immutable authority-none report."""
    checkpoint, checkpoint_evidence = _read_json_object(args.checkpoint)
    rows, ledger_evidence = _read_matching_routing_prefix(args.decision_ledger)
    generator = _generator_identity()
    report = build_v58_brentoil_opposite_exit_audit(checkpoint, rows, ledger_evidence)
    report["source_evidence"] = {
        "checkpoint": checkpoint_evidence,
        "decision_ledger_prefix": ledger_evidence,
    }
    report["generator_identity"] = generator
    _require_prefix_unchanged(args.decision_ledger, ledger_evidence)
    if _generator_identity() != generator:
        raise ValueError("BRENTOIL audit generator changed during evaluation")
    _require_authority_none(report)
    write_immutable_json(args.out, report)
    return report


def _read_matching_routing_prefix(
    path: Path,
) -> tuple[tuple[Record, ...], Record]:
    if not path.is_file():
        raise FileNotFoundError(f"V58 decision ledger is missing: {path}")
    length = _complete_prefix_size(path)
    if length < 1:
        raise ValueError("V58 decision ledger has no complete rows")
    hasher = hashlib.sha256()
    matches: list[Record] = []
    row_count = 0
    consumed = 0
    with path.open("rb") as stream:
        while consumed < length:
            line = stream.readline(length - consumed)
            if not line or not line.endswith(b"\n"):
                raise ValueError("V58 decision ledger prefix changed during read")
            consumed += len(line)
            hasher.update(line)
            row_count += 1
            if _STRATEGY_NEEDLE in line:
                matches.append(_json_record(line, row_count))
    return tuple(matches), {
        "path": str(path.resolve()),
        "bytes": length,
        "sha256": hasher.hexdigest(),
        "rows": row_count,
        "matching_rows": len(matches),
    }


def _complete_prefix_size(path: Path) -> int:
    size = path.stat().st_size
    if size == 0:
        return 0
    with path.open("rb") as stream:
        stream.seek(size - 1)
        if stream.read(1) == b"\n":
            return size
        cursor = size
        while cursor > 0:
            start = max(0, cursor - 64 * 1024)
            stream.seek(start)
            block = stream.read(cursor - start)
            boundary = block.rfind(b"\n")
            if boundary >= 0:
                return start + boundary + 1
            cursor = start
    return 0


def _require_prefix_unchanged(path: Path, evidence: Mapping[str, object]) -> None:
    length = _integer(evidence.get("bytes"), "decision ledger prefix bytes")
    hasher = hashlib.sha256()
    remaining = length
    with path.open("rb") as stream:
        while remaining:
            block = stream.read(min(1024 * 1024, remaining))
            if not block:
                raise ValueError("V58 decision ledger changed during evaluation")
            hasher.update(block)
            remaining -= len(block)
    if hasher.hexdigest() != evidence.get("sha256"):
        raise ValueError("V58 decision ledger changed during evaluation")


def _read_json_object(path: Path) -> tuple[Record, Record]:
    if not path.is_file():
        raise FileNotFoundError(f"V58 checkpoint is missing: {path}")
    content = path.read_bytes()
    value = json.loads(content)
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("V58 checkpoint must be a JSON object")
    return cast(Record, value), {
        "path": str(path.resolve()),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _json_record(line: bytes, line_number: int) -> Record:
    value = json.loads(line)
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"V58 decision ledger row {line_number} must be an object")
    return cast(Record, value)


def _generator_identity() -> list[Record]:
    paths = (
        Path(__file__).resolve(),
        _ROOT / "src/hypervector/research/v58_brentoil_opposite_exit_audit.py",
        _ROOT / "src/hypervector/data/oxa_storage.py",
    )
    return [{"path": str(path.resolve()), **file_evidence(path)} for path in paths]


def _require_authority_none(report: Mapping[str, object]) -> None:
    contract = report.get("contract")
    safe = (
        isinstance(contract, Mapping)
        and contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and contract.get("automatic_strategy_changes") is False
        and contract.get("runtime_strategy_changed") is False
    )
    if not safe:
        raise ValueError("V58 BRENTOIL audit authority contract is invalid")


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def main() -> int:
    """Run the immutable report-only audit."""
    publish_report(build_parser().parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
