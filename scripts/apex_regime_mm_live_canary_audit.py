#!/usr/bin/env python3
"""Publish immutable, report-only evidence for one Apex MM live run."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.apex_mm_live_audit import audit_apex_mm_live_run
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit one Apex MM live ledger without execution authority."
    )
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _publish(args: argparse.Namespace) -> dict[str, object]:
    if args.out.exists():
        raise FileExistsError(f"immutable live audit output exists: {args.out}")
    with snapshot_decision_ledger(args.decisions) as (rows, evidence):
        report = audit_apex_mm_live_run(rows, run_id=args.run_id)
    report["evidence"] = {"decisions": evidence}
    write_immutable_json(args.out, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Publish sparse, losing, or favorable canary evidence without gating it."""
    args = _parser().parse_args(argv)
    report = _publish(args)
    run = report.get("run")
    execution = report.get("execution")
    if not isinstance(run, dict) or not isinstance(execution, dict):
        raise RuntimeError("Apex MM live audit returned an invalid report structure")
    print(
        json.dumps(
            {
                "out": str(args.out),
                "run_id": run.get("run_id"),
                "fills": execution.get("fills"),
                "report_only": True,
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
