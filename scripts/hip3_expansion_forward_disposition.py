#!/usr/bin/env python3
"""Publish a source-bound report-only HIP-3 expansion disposition."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import cast

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_expansion_forward_disposition import (
    Hip3ExpansionEvidence,
    build_hip3_expansion_forward_disposition,
)

_NAMES = (
    "development",
    "path_repair",
    "candle_parity",
    "signal_parity",
    "observer_parity",
    "markouts",
)


@dataclass(frozen=True)
class _CandidatePaths:
    symbol: str
    paths: Mapping[str, Path]


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit immutable disposition parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate",
        nargs=7,
        action="append",
        required=True,
        metavar=(
            "SYMBOL",
            "DEVELOPMENT",
            "PATH_REPAIR",
            "CANDLE_PARITY",
            "SIGNAL_PARITY",
            "OBSERVER_PARITY",
            "MARKOUTS",
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_command(args: argparse.Namespace) -> dict[str, object]:
    """Validate exact inputs and publish one authority-none disposition."""
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"HIP-3 expansion output already exists: {output}")
    candidates = tuple(_candidate_paths(row) for row in args.candidate)
    _require_distinct(candidates, output)
    evidence = _evidence(candidates)
    reports = tuple(_load_candidate(candidate) for candidate in candidates)
    report = build_hip3_expansion_forward_disposition(reports)
    _require_unchanged(candidates, evidence)
    report["input_evidence"] = _input_evidence(candidates, evidence)
    report["generator_identity"] = _generator_identity()
    write_immutable_json(output, report)
    return report


def _candidate_paths(values: Sequence[str]) -> _CandidatePaths:
    if len(values) != 7:
        raise ValueError("HIP-3 expansion candidate requires seven values")
    symbol = values[0]
    paths = {name: Path(value) for name, value in zip(_NAMES, values[1:], strict=True)}
    return _CandidatePaths(symbol, paths)


def _load_candidate(candidate: _CandidatePaths) -> Hip3ExpansionEvidence:
    reports = {name: _json_object(path, name) for name, path in candidate.paths.items()}
    return Hip3ExpansionEvidence(
        symbol=candidate.symbol,
        development=reports["development"],
        path_repair=reports["path_repair"],
        candle_parity=reports["candle_parity"],
        signal_parity=reports["signal_parity"],
        observer_parity=reports["observer_parity"],
        markouts=reports["markouts"],
    )


def _json_object(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"HIP-3 expansion {label} is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"HIP-3 expansion {label} must be an object")
    return cast(dict[str, object], value)


def _evidence(
    candidates: Sequence[_CandidatePaths],
) -> dict[str, dict[str, Mapping[str, object]]]:
    return {
        candidate.symbol: {
            name: file_evidence(path) for name, path in candidate.paths.items()
        }
        for candidate in candidates
    }


def _require_unchanged(
    candidates: Sequence[_CandidatePaths],
    evidence: Mapping[str, Mapping[str, Mapping[str, object]]],
) -> None:
    for candidate in candidates:
        expected = evidence[candidate.symbol]
        for name, path in candidate.paths.items():
            if file_evidence(path) != dict(expected[name]):
                raise ValueError(f"HIP-3 expansion {candidate.symbol} {name} changed")


def _input_evidence(
    candidates: Sequence[_CandidatePaths],
    evidence: Mapping[str, Mapping[str, Mapping[str, object]]],
) -> dict[str, object]:
    return {
        candidate.symbol: {
            name: {
                "path": str(path.resolve()),
                **dict(evidence[candidate.symbol][name]),
            }
            for name, path in candidate.paths.items()
        }
        for candidate in candidates
    }


def _require_distinct(candidates: Sequence[_CandidatePaths], output: Path) -> None:
    paths = [
        path.resolve() for candidate in candidates for path in candidate.paths.values()
    ]
    paths.append(output.resolve())
    if len(set(paths)) != len(paths):
        raise ValueError("HIP-3 expansion input and output paths must be distinct")
    symbols = [candidate.symbol for candidate in candidates]
    if len(set(symbols)) != len(symbols):
        raise ValueError("HIP-3 expansion candidate symbols must be unique")


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    sources = (
        Path(__file__).resolve(),
        root / "src/hypervector/research/hip3_expansion_forward_disposition.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in sources}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only disposition publisher."""
    args = build_parser().parse_args(argv)
    try:
        report = run_command(args)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "candidate_count": report["candidate_count"],
                "research_priority_order": report["research_priority_order"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
