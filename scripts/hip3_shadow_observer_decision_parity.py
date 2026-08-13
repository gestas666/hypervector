#!/usr/bin/env python3
"""Publish immutable HIP-3 archive-versus-observer decision parity."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_shadow_observer_decision_parity import (
    build_hip3_shadow_observer_decision_parity,
)
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger

Record = Mapping[str, object]

_GENERATOR_FILES = (
    Path(__file__).resolve(),
    Path("src/hypervector/research/hip3_shadow_observer_decision_parity.py").resolve(),
    Path("src/hypervector/research/live_ledger_snapshot.py").resolve(),
    Path("src/hypervector/data/oxa_storage.py").resolve(),
)


def build_parser() -> argparse.ArgumentParser:
    """Build explicit immutable report arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal-parity", type=Path, required=True)
    parser.add_argument("--observer-journal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Snapshot inputs and build one authority-none parity report."""
    paths = {
        "signal_parity": Path(args.signal_parity),
        "observer_journal": Path(args.observer_journal),
    }
    _validate_paths(paths, Path(args.output))
    generator = {"files": _generator_identity()}
    signal = _json_object(paths["signal_parity"], "signal parity")
    signal_evidence = file_evidence(paths["signal_parity"])
    with snapshot_decision_ledger(
        paths["observer_journal"], allow_incomplete_tail=True
    ) as (rows, journal_evidence):
        report = build_hip3_shadow_observer_decision_parity(
            signal_parity_report=signal,
            observer_rows=rows,
        )
    _require_unchanged(paths["signal_parity"], signal_evidence)
    report.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "input_evidence": {
                "signal_parity": _path_evidence(
                    paths["signal_parity"], signal_evidence
                ),
                "observer_journal": _path_evidence(
                    paths["observer_journal"], journal_evidence
                ),
            },
            "generator_identity": generator,
        }
    )
    report["material_state_sha256"] = _digest(report)
    return report


def publish_report(path: Path, report: Record) -> None:
    """Publish one immutable parity artifact."""
    write_immutable_json(path, report)


def _validate_paths(paths: Mapping[str, Path], output: Path) -> None:
    resolved = [path.resolve() for path in (*paths.values(), output)]
    if len(set(resolved)) != len(resolved):
        raise ValueError("parity input and output paths must be distinct")


def _json_object(path: Path, label: str) -> dict[str, object]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _path_evidence(path: Path, evidence: Record) -> dict[str, object]:
    return {**evidence, "path": str(path.resolve())}


def _require_unchanged(path: Path, expected: Record) -> None:
    current = file_evidence(path)
    if current != expected:
        raise RuntimeError(f"parity input changed during evaluation: {path}")


def _generator_identity() -> list[dict[str, object]]:
    return [_file_record(path) for path in _GENERATOR_FILES]


def _require_unchanged_generator(expected: Record) -> None:
    files = expected.get("files")
    if not isinstance(files, list) or files != _generator_identity():
        raise RuntimeError("parity generator changed during evaluation")


def _file_record(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _digest(report: Record) -> str:
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Build, revalidate, and publish one immutable report."""
    args = build_parser().parse_args(argv)
    report = run_report(args)
    _require_unchanged_generator(
        _mapping(report.get("generator_identity"), "generator identity")
    )
    publish_report(Path(args.output), report)
    assessment = _mapping(report.get("technical_assessment"), "assessment")
    print(
        json.dumps(
            {
                "event": "hip3_shadow_observer_decision_parity",
                "state": "published",
                "output": str(args.output),
                "mismatches": assessment.get("pressure_decision_mismatches"),
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
