#!/usr/bin/env python3
"""Publish an immutable report-only delta between two cohort live audits."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from pathlib import Path
import sys

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.cohort_live_audit_delta import build_live_audit_delta

Record = Mapping[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable audit-prefix delta command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def publish(args: argparse.Namespace) -> tuple[dict[str, object], Path]:
    """Build and publish one immutable report-only audit delta."""
    before_path = _path(args.before, "before audit")
    after_path = _path(args.after, "after audit")
    output = _path(args.out, "delta output")
    if output.exists():
        raise FileExistsError(f"immutable delta output exists: {output}")
    before, before_evidence = _load_audit(before_path)
    after, after_evidence = _load_audit(after_path)
    report = build_live_audit_delta(before, after)
    report["source_evidence"] = {
        "before": before_evidence,
        "after": after_evidence,
    }
    write_immutable_json(output, report)
    return report, output


def _load_audit(path: Path) -> tuple[Record, dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(f"audit file is missing: {path}")
    raw = path.read_bytes()
    audit = _mapping(json.loads(raw), f"audit {path}")
    return audit, {
        "path": str(path),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must contain a JSON object")
    return value


def _path(value: object, label: str) -> Path:
    if not isinstance(value, Path):
        raise TypeError(f"{label} must be a path")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Publish one delta and print a bounded operational summary."""
    try:
        report, output = publish(build_parser().parse_args(argv))
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        print(f"audit delta refused: {exc}", file=sys.stderr)
        return 2
    resolved = _mapping(report.get("resolved_execution"), "resolved delta")
    technical = _mapping(report.get("technical_coverage"), "technical delta")
    bbo = _mapping(
        report.get("executable_bbo_episode_maturity"),
        "executable BBO maturity delta",
    )
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(output),
                "closed_trades_delta": resolved.get("closed_trades_delta"),
                "metric_value_gaps_delta": technical.get("metric_value_gaps_delta"),
                "newly_matured_executable_bbo_episode_onsets": bbo.get(
                    "newly_matured_episode_onsets"
                ),
                "executable_bbo_path_identity_complete": bbo.get(
                    "path_identity_complete"
                ),
                "execution_authority": "none",
                "runtime_strategy_changed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
