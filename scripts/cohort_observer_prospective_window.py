#!/usr/bin/env python3
"""Publish an immutable cutoff-bound audit for one disarmed observer."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.cohort_observer_audit import audit_cohort_observer_run
from hypervector.research.cohort_observer_prospective_window import (
    build_observer_prospective_window,
)
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable prospective-window parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--start-ms", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def publish_window(args: argparse.Namespace) -> dict[str, object]:
    """Snapshot, validate, and publish one prospective observer prefix."""
    if args.out.exists():
        raise FileExistsError(f"prospective observer output exists: {args.out}")
    with snapshot_decision_ledger(args.decisions) as (records, evidence):
        audit = audit_cohort_observer_run(records, run_id=args.run_id)
        report = build_observer_prospective_window(
            records,
            audit,
            start_ms=args.start_ms,
        )
    report["evidence"] = {"path": str(args.decisions), **evidence}
    write_immutable_json(args.out, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Publish the report without constructing execution clients."""
    args = build_parser().parse_args(argv)
    report = publish_window(args)
    print(
        json.dumps(
            {
                "out": str(args.out),
                "status": report["status"],
                "evaluations": report["signals"]["evaluations"],
                "eligible_evaluations": report["signals"]["eligible_evaluations"],
                "report_only": True,
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
