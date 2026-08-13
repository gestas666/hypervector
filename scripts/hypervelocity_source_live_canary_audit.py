#!/usr/bin/env python3
"""Publish immutable, report-only evidence for one source-follow live run."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger
from hypervector.research.source_follow_live_audit import (
    audit_source_follow_live_run,
)


_ledger_snapshot = snapshot_decision_ledger


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit one live source-follow ledger without execution authority."
    )
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _experiment_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }


def _report(args: argparse.Namespace) -> dict[str, object]:
    with _ledger_snapshot(args.decisions) as (rows, decisions_evidence):
        report = audit_source_follow_live_run(
            rows,
            database_path=args.database,
            run_id=args.run_id,
        )
    report.update(_experiment_contract())
    report["evidence"] = {
        "decisions": decisions_evidence,
        "database": file_evidence(args.database),
    }
    return report


def _publish(args: argparse.Namespace) -> dict[str, object]:
    if args.out.exists():
        raise FileExistsError(f"immutable live audit output exists: {args.out}")
    report = _report(args)
    write_immutable_json(args.out, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Publish a live-canary audit; sparse or losing results are still valid."""
    args = _parser().parse_args(argv)
    report = _publish(args)
    run = report["run"]
    decisions = report["decisions"]
    if not isinstance(run, dict) or not isinstance(decisions, dict):
        raise RuntimeError("live audit returned an invalid report structure")
    print(
        json.dumps(
            {
                "out": str(args.out),
                "run_id": run.get("run_id"),
                "decision_rows": decisions.get("rows"),
                **_experiment_contract(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
