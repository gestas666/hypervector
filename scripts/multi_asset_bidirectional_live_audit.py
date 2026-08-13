#!/usr/bin/env python3
"""Publish immutable, report-only evidence for one shared cohort live run."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from contextlib import ExitStack
import json
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.cohort_live_audit import audit_multi_asset_live_run
from hypervector.research.cohort_live_audit_values import configured_symbols
from hypervector.research.cohort_live_audit_values import run_id as audit_run_id
from hypervector.research.cohort_live_run_selection import select_armed_live_run
from hypervector.research.cohort_historical_asset_ledgers import (
    snapshot_retired_asset_ledgers,
)
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit one multi-asset live cohort without execution authority."
    )
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--run-id")
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--out", type=Path)
    destination.add_argument("--out-dir", type=Path)
    return parser


def _publish(args: argparse.Namespace) -> tuple[dict[str, object], Path]:
    cohort_path = args.ledger_root / "decisions.jsonl"
    with ExitStack() as stack:
        cohort_rows, cohort_evidence = stack.enter_context(
            snapshot_decision_ledger(cohort_path)
        )
        _, identity = select_armed_live_run(cohort_rows, args.run_id)
        asset_paths = _asset_paths(
            args.ledger_root,
            cohort_path,
            configured_symbols(identity),
        )
        assets: dict[str, list[dict[str, object]]] = {}
        evidence: dict[str, dict[str, object]] = {}
        for symbol, path in asset_paths.items():
            rows, facts = stack.enter_context(snapshot_decision_ledger(path))
            assets[symbol] = rows
            evidence[symbol] = {"path": str(path), **facts}
        retired, retired_evidence = snapshot_retired_asset_ledgers(
            stack,
            args.ledger_root,
            cohort_path,
            active_symbols=tuple(asset_paths),
            compatible_execution_history=False,
            run_id=audit_run_id(identity),
        )
        report = audit_multi_asset_live_run(
            cohort_rows,
            assets,
            all_time_asset_records=assets | retired,
            run_id=args.run_id,
        )
    report["evidence"] = {
        "cohort": {"path": str(cohort_path), **cohort_evidence},
        "assets": evidence,
        "retired_assets": retired_evidence,
    }
    output = _output_path(args, report)
    if output.exists():
        raise FileExistsError(f"immutable cohort audit output exists: {output}")
    write_immutable_json(output, report)
    return report, output


def _asset_paths(
    ledger_root: Path,
    cohort_path: Path,
    symbols: tuple[str, ...],
) -> dict[str, Path]:
    """Resolve canonical symbols to their configured lower-case ledger paths."""
    paths = {symbol: ledger_root / f"{symbol.lower()}.jsonl" for symbol in symbols}
    missing = [symbol for symbol, path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            f"missing configured asset ledgers: {', '.join(missing)}"
        )
    if cohort_path in paths.values():
        raise ValueError("configured asset ledger collides with cohort ledger")
    return paths


def _output_path(args: argparse.Namespace, report: dict[str, object]) -> Path:
    if isinstance(args.out, Path):
        return args.out
    run = report.get("run")
    if not isinstance(run, dict) or not isinstance(run.get("run_id"), str):
        raise RuntimeError("cohort live audit did not report a run identifier")
    if not isinstance(args.out_dir, Path):
        raise RuntimeError("cohort live audit output destination is missing")
    return args.out_dir / f"multi_asset_live_audit_{run['run_id']}.json"


def main(argv: Sequence[str] | None = None) -> int:
    """Publish quiet, losing, incomplete, or favorable evidence unchanged."""
    args = _parser().parse_args(argv)
    report, output = _publish(args)
    run = report.get("run")
    execution = report.get("execution")
    coverage = report.get("coverage")
    if not all(isinstance(value, dict) for value in (run, execution, coverage)):
        raise RuntimeError("cohort live audit returned an invalid report structure")
    print(
        json.dumps(
            {
                "out": str(output),
                "run_id": run.get("run_id"),
                "closed_trades": execution.get("closed_trades"),
                "net_pnl_usd": execution.get("net_pnl_usd"),
                "evidence_complete": coverage.get("complete"),
                "report_only": True,
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
