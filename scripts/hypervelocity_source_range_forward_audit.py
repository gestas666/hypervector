#!/usr/bin/env python3
"""Publish forward paths after one live run's RANGE decisions."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger
from hypervector.research.source_follow_range_forward import (
    audit_range_forward_paths,
    extract_range_decisions,
)


_DEFAULT_HORIZONS = (5, 15, 30, 60)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit forward paths after live RANGE decisions without trades."
    )
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--target-price-fraction", type=float, required=True)
    parser.add_argument("--horizon-minutes", type=int, action="append")
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _report(args: argparse.Namespace) -> dict[str, object]:
    with snapshot_decision_ledger(args.decisions) as (rows, ledger_evidence):
        decisions = extract_range_decisions(rows, run_id=args.run_id)
        report = audit_range_forward_paths(
            args.database,
            decisions,
            symbol=args.symbol,
            target_price_fraction=args.target_price_fraction,
            horizons_minutes=tuple(args.horizon_minutes or _DEFAULT_HORIZONS),
        )
    report["run_id"] = args.run_id
    report["evidence"] = {
        "decisions": ledger_evidence,
        "database": file_evidence(args.database),
    }
    return report


def _publish(args: argparse.Namespace) -> dict[str, object]:
    if args.out.exists():
        raise FileExistsError(f"immutable RANGE audit output exists: {args.out}")
    report = _report(args)
    write_immutable_json(args.out, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Publish one report-only live RANGE forward-path audit."""
    args = _parser().parse_args(argv)
    report = _publish(args)
    print(
        json.dumps(
            {
                "out": str(args.out),
                "run_id": report["run_id"],
                "decision_rows": report["decision_rows"],
                "report_only": report["report_only"],
                "execution_authority": report["execution_authority"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
