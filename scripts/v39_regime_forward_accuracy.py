#!/usr/bin/env python3
"""Publish exact causal forward diagnostics for v39 regime observations."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger
from hypervector.research.v39_regime_forward_accuracy import (
    build_v39_regime_forward_accuracy,
)

Record = Mapping[str, object]

_LEDGER = Path("data/live/bidirectional_cohort/decisions.jsonl")
_GENERATOR_FILES = (
    Path(__file__).resolve(),
    Path("src/hypervector/research/v39_regime_forward_accuracy.py").resolve(),
    Path("src/hypervector/research/v39_forward_evidence_contract.py").resolve(),
    Path("src/hypervector/research/live_ledger_snapshot.py").resolve(),
    Path("src/hypervector/data/oxa_storage.py").resolve(),
)


def build_parser() -> argparse.ArgumentParser:
    """Build explicit source, run, diagnostic, and output arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=_LEDGER)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--horizons-minutes",
        type=int,
        nargs="+",
        default=(5, 15, 30, 60),
    )
    parser.add_argument(
        "--range-thresholds-bps",
        type=float,
        nargs="+",
        default=(10.0, 25.0, 50.0),
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Snapshot the append-only ledger and build an authority-none report."""
    _validate_paths(args.ledger, args.out)
    identity = {"files": _generator_identity()}
    with snapshot_decision_ledger(
        args.ledger,
        run_id=args.run_id,
        allow_incomplete_tail=True,
    ) as (rows, ledger_evidence):
        report = build_v39_regime_forward_accuracy(
            rows,
            run_id=args.run_id,
            horizons_minutes=args.horizons_minutes,
            range_thresholds_bps=args.range_thresholds_bps,
        )
        evidence = {**ledger_evidence, "path": str(args.ledger.resolve())}
    report.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "evidence": {"ledger": evidence},
            "generator_identity": identity,
        }
    )
    report["material_state_sha256"] = _digest(report)
    return report


def publish_report(path: Path, report: Record) -> None:
    """Publish deterministic JSON without replacing earlier evidence."""
    write_immutable_json(path, report)


def _validate_paths(ledger: Path, output: Path) -> None:
    if ledger.resolve() == output.resolve():
        raise ValueError("v39 regime output must differ from its live ledger input")


def _generator_identity() -> list[dict[str, object]]:
    return [_file_record(path) for path in _GENERATOR_FILES]


def _require_unchanged_generator(expected: Record) -> None:
    files = expected.get("files")
    if not isinstance(files, list) or files != _generator_identity():
        raise RuntimeError("v39 regime diagnostic generator changed during evaluation")


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
    """Build, revalidate, and publish one immutable regime diagnostic."""
    args = build_parser().parse_args(argv)
    report = run_report(args)
    _require_unchanged_generator(
        _mapping(report.get("generator_identity"), "generator identity")
    )
    publish_report(args.out, report)
    source = _mapping(report.get("source"), "regime source")
    print(
        json.dumps(
            {
                "event": "v39_regime_forward_accuracy",
                "state": "published",
                "output": str(args.out),
                "observations": source.get("unique_observations"),
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
