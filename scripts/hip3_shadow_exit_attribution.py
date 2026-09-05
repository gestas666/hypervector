#!/usr/bin/env python3
"""Publish immutable report-only HIP-3 lifecycle exit attribution."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import sys
from typing import cast

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_shadow_exit_attribution import (
    build_hip3_shadow_exit_attribution,
)

Record = Mapping[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit report-only attribution command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lifecycle-report", type=Path, required=True)
    parser.add_argument("--markout-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_command(args: argparse.Namespace) -> dict[str, object]:
    """Bind immutable evidence and publish one authority-none measurement."""
    lifecycle_path = Path(args.lifecycle_report)
    markout_path = Path(args.markout_report)
    output = Path(args.output)
    _require_distinct((lifecycle_path, markout_path, output))
    _require_new_output(output)
    paths = {
        "lifecycle_report": lifecycle_path,
        "markout_report": markout_path,
    }
    evidence = {name: file_evidence(path) for name, path in paths.items()}
    report = build_hip3_shadow_exit_attribution(
        _json_object(lifecycle_path, "lifecycle report"),
        _json_object(markout_path, "markout report"),
    )
    _require_unchanged(paths, evidence)
    report["input_evidence"] = _input_evidence(paths, evidence)
    report["generator_identity"] = _generator_identity()
    write_immutable_json(output, report)
    return report


def _json_object(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"HIP-3 exit attribution {label} is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"HIP-3 exit attribution {label} must be an object")
    return cast(dict[str, object], value)


def _require_distinct(paths: Sequence[Path]) -> None:
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError(
            "HIP-3 exit attribution input and output paths must be distinct"
        )


def _require_new_output(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"immutable JSON output exists: {path}")


def _require_unchanged(
    paths: Mapping[str, Path], evidence: Mapping[str, Mapping[str, object]]
) -> None:
    for name, path in paths.items():
        if file_evidence(path) != dict(evidence[name]):
            raise ValueError(f"HIP-3 exit attribution {name} changed during evaluation")


def _input_evidence(
    paths: Mapping[str, Path], evidence: Mapping[str, Mapping[str, object]]
) -> dict[str, object]:
    return {
        name: {"path": str(path.resolve()), **dict(evidence[name])}
        for name, path in paths.items()
    }


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/research/hip3_shadow_exit_attribution.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in paths}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the diagnostic and print a compact non-authoritative summary."""
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
                "output": str(Path(args.output).resolve()),
                "symbol": report["symbol"],
                "summary": report["summary"],
                "execution_authority": "none",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
