#!/usr/bin/env python3
"""Publish immutable setup-process evidence for one disarmed cohort run."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import sys

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.cohort_observer_audit import audit_cohort_observer_run
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger

# The paper observer ledger (paper observe's default ledger root), never the
# live cohort ledger.
_DEFAULT_DECISIONS = Path("data/paper/cohort/decisions.jsonl")


def build_parser() -> argparse.ArgumentParser:
    """Build the read-only observer audit command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=Path, default=_DEFAULT_DECISIONS)
    parser.add_argument("--run-id")
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--out", type=Path)
    destination.add_argument("--out-dir", type=Path)
    return parser


def publish_observer_audit(
    args: argparse.Namespace,
) -> tuple[dict[str, object], Path]:
    """Snapshot, audit, and immutably publish one disarmed run."""
    with snapshot_decision_ledger(args.decisions) as (records, evidence):
        report = audit_cohort_observer_run(records, run_id=args.run_id)
    report["evidence"] = {"path": str(args.decisions), **evidence}
    output = _output_path(args, report)
    if output.exists():
        raise FileExistsError(f"observer audit output exists: {output}")
    write_immutable_json(output, report)
    return report, output


def _output_path(args: argparse.Namespace, report: dict[str, object]) -> Path:
    if isinstance(args.out, Path):
        return args.out
    run = report.get("run")
    if not isinstance(run, dict) or not isinstance(run.get("run_id"), str):
        raise RuntimeError("observer audit did not report a run identifier")
    if not isinstance(args.out_dir, Path):
        raise RuntimeError("observer audit output destination is missing")
    return args.out_dir / f"multi_asset_observer_audit_{run['run_id']}.json"


def main(argv: Sequence[str] | None = None) -> int:
    """Publish setup diagnostics without execution or performance authority.

    A missing ledger, an existing output or another technical failure prints
    the CLI's shared JSON error document (``command: "paper audit"``), exit 1.
    """
    try:
        report, output = publish_observer_audit(build_parser().parse_args(argv))
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "command": "paper audit",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            ),
            file=sys.stderr,
        )
        return 1
    run = report.get("run")
    runtime = report.get("runtime")
    technical = report.get("technical")
    signals = report.get("signals")
    if not all(isinstance(value, dict) for value in (run, runtime, technical, signals)):
        raise RuntimeError("observer audit returned an invalid report structure")
    print(
        json.dumps(
            {
                "out": str(output),
                "run_id": run.get("run_id"),
                "poll_cycles": runtime.get("poll_cycles"),
                "technical_complete": technical.get("complete"),
                "strategy_intents": signals.get("strategy_intents"),
                "report_only": True,
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
