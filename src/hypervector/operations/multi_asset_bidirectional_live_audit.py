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
    parser.add_argument(
        "--history-scope",
        choices=("all-time", "current-run"),
        default="all-time",
        help="Snapshot all compatible history or only the explicitly selected run.",
    )
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--out", type=Path)
    destination.add_argument("--out-dir", type=Path)
    return parser


def _publish(args: argparse.Namespace) -> tuple[dict[str, object], Path]:
    cohort_path = args.ledger_root / "decisions.jsonl"
    history_scope = _history_scope(args)
    selected_run = _snapshot_run_id(args, history_scope)
    with ExitStack() as stack:
        cohort_rows, cohort_evidence = stack.enter_context(
            snapshot_decision_ledger(cohort_path, run_id=selected_run)
        )
        cohort_rows, cohort_evidence = _rebased_current_run_snapshot(
            cohort_rows, cohort_evidence, "cohort", selected_run
        )
        _, identity = select_armed_live_run(cohort_rows, args.run_id)
        asset_paths = _asset_paths(
            args.ledger_root,
            cohort_path,
            configured_symbols(identity),
        )
        assets, evidence = _snapshot_assets(stack, asset_paths, selected_run)
        retired, retired_evidence = _retired_history(
            stack, args, cohort_path, asset_paths, identity, history_scope
        )
        report = audit_multi_asset_live_run(
            cohort_rows,
            assets,
            all_time_asset_records=assets | retired,
            run_id=args.run_id,
        )
    report["evidence"] = {
        "history_scope": history_scope,
        "cohort": {"path": str(cohort_path), **cohort_evidence},
        "assets": evidence,
        "retired_assets": retired_evidence,
    }
    output = _output_path(args, report)
    if output.exists():
        raise FileExistsError(f"immutable cohort audit output exists: {output}")
    write_immutable_json(output, report)
    return report, output


def _history_scope(args: argparse.Namespace) -> str:
    value = getattr(args, "history_scope", "all-time")
    if value not in {"all-time", "current-run"}:
        raise ValueError("history scope must be all-time or current-run")
    return value


def _snapshot_run_id(args: argparse.Namespace, history_scope: str) -> str | None:
    if history_scope == "all-time":
        return None
    if not isinstance(args.run_id, str) or not args.run_id:
        raise ValueError("current-run history scope requires --run-id")
    return args.run_id


def _snapshot_assets(
    stack: ExitStack,
    asset_paths: dict[str, Path],
    run_id: str | None,
) -> tuple[dict[str, list[dict[str, object]]], dict[str, dict[str, object]]]:
    assets: dict[str, list[dict[str, object]]] = {}
    evidence: dict[str, dict[str, object]] = {}
    for symbol, path in asset_paths.items():
        rows, facts = stack.enter_context(snapshot_decision_ledger(path, run_id=run_id))
        rows, facts = _rebased_current_run_snapshot(rows, facts, symbol, run_id)
        assets[symbol] = rows
        evidence[symbol] = {"path": str(path), **facts}
    return assets, evidence


def _rebased_current_run_snapshot(
    rows: list[dict[str, object]],
    evidence: dict[str, object],
    label: str,
    run_id: str | None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    if run_id is None:
        return rows, evidence
    if not rows:
        raise ValueError(f"{label} current-run snapshot contains no records")
    source_start = rows[0].get("sequence")
    if (
        isinstance(source_start, bool)
        or not isinstance(source_start, int)
        or source_start < 1
    ):
        raise ValueError(f"{label} current-run source sequence is invalid")
    for expected, row in enumerate(rows, source_start):
        if row.get("sequence") != expected:
            raise ValueError(f"{label} source sequence is not contiguous at {expected}")
    rebased = [{**row, "sequence": index} for index, row in enumerate(rows, 1)]
    facts = {
        **evidence,
        "source_sequence_start": source_start,
        "source_sequence_end": source_start + len(rows) - 1,
        "snapshot_sequence_rebased": True,
    }
    return rebased, facts


def _retired_history(
    stack: ExitStack,
    args: argparse.Namespace,
    cohort_path: Path,
    asset_paths: dict[str, Path],
    identity: dict[str, object],
    history_scope: str,
) -> tuple[dict[str, list[dict[str, object]]], dict[str, dict[str, object]]]:
    if history_scope == "current-run":
        return {}, {}
    return snapshot_retired_asset_ledgers(
        stack,
        args.ledger_root,
        cohort_path,
        active_symbols=tuple(asset_paths),
        compatible_execution_history=False,
        run_id=audit_run_id(identity),
    )


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
