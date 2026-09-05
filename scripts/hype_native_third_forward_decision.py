#!/usr/bin/env python3
"""Apply the frozen HYPE-native third-forward decision rule report-only."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hype_native_third_forward_decision import (
    decide_hype_native_third_forward,
)

_GENERATOR_PATHS = tuple(
    Path(value).resolve()
    for value in (
        __file__,
        "src/hypervector/research/hype_native_third_forward_decision.py",
        "src/hypervector/research/cohort_change_proposals.py",
        "src/hypervector/data/oxa_storage.py",
    )
)


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable immutable decision parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolution", type=Path, required=True)
    parser.add_argument("--preregistered-journal", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Evaluate exact frozen files and reject input or generator drift."""
    inputs = _input_evidence(args)
    generator = _generator_evidence()
    resolution = _json_object(args.resolution, "HYPE exact resolution")
    journal = _json_object(args.preregistered_journal, "HYPE preregistered journal")
    report = decide_hype_native_third_forward(resolution, journal)
    if inputs != _input_evidence(args):
        raise RuntimeError("HYPE third-forward decision inputs changed")
    if generator != _generator_evidence():
        raise RuntimeError("HYPE third-forward decision generator changed")
    report["evidence"] = inputs | {"generator_files": generator}
    return report


def _input_evidence(args: argparse.Namespace) -> dict[str, object]:
    return {
        "resolution": _file_record(args.resolution),
        "preregistered_journal": _file_record(args.preregistered_journal),
    }


def _generator_evidence() -> list[dict[str, object]]:
    return [_file_record(path) for path in _GENERATOR_PATHS]


def _file_record(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _json_object(path: Path, label: str) -> Mapping[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Publish one immutable decision with no execution authority."""
    args = build_parser().parse_args(argv)
    report = run(args)
    write_immutable_json(args.out, report)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "decision": report["decision"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
