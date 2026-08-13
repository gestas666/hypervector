#!/usr/bin/env python3
"""Recover legacy Apex MM fill TIDs and publish an immutable live audit."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.live.hyperliquid_btc_factory import create_read_only_btc_reader
from hypervector.research.apex_mm_legacy_fill_recovery import (
    recover_legacy_apex_fill_trade_ids,
)
from hypervector.research.apex_mm_live_audit import audit_apex_mm_live_run
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger
from hypervector.runtime_env import load_wallet_env_if_present


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit legacy Apex fills against read-only Hyperliquid truth."
    )
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _publish(args: argparse.Namespace) -> dict[str, object]:
    if args.out.exists():
        raise FileExistsError(f"immutable live audit output exists: {args.out}")
    venue_fills = create_read_only_btc_reader().fills()
    with snapshot_decision_ledger(args.decisions) as (rows, ledger_evidence):
        recovered, recovery_evidence = recover_legacy_apex_fill_trade_ids(
            rows,
            venue_fills=venue_fills,
            run_id=args.run_id,
        )
        report = audit_apex_mm_live_run(recovered, run_id=args.run_id)
    report["evidence"] = {
        "decisions": ledger_evidence,
        "venue_fill_recovery": recovery_evidence,
    }
    write_immutable_json(args.out, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Load only public identity and publish exact legacy-fill evidence."""
    args = _parser().parse_args(argv)
    load_wallet_env_if_present()
    report = _publish(args)
    run = report.get("run")
    execution = report.get("execution")
    evidence = report.get("evidence")
    if not all(isinstance(value, dict) for value in (run, execution, evidence)):
        raise RuntimeError("legacy Apex audit returned an invalid report structure")
    recovery = evidence.get("venue_fill_recovery")
    if not isinstance(recovery, dict):
        raise RuntimeError("legacy Apex audit omitted venue recovery evidence")
    print(
        json.dumps(
            {
                "out": str(args.out),
                "run_id": run.get("run_id"),
                "fills": execution.get("fills"),
                "recovered_trade_ids": recovery.get("recovered_fill_count"),
                "report_only": True,
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
