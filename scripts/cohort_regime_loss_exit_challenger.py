#!/usr/bin/env python3
"""Publish immutable report-only regime-opposition loss-exit evidence."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
import json
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.cohort_live_audit import audit_multi_asset_live_run
from hypervector.research.cohort_live_audit_values import configured_symbols
from hypervector.research.cohort_live_run_selection import select_armed_live_run
from hypervector.research.cohort_regime_loss_exit_challenger import (
    build_regime_loss_exit_challenger,
)
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger

Record = Mapping[str, object]
_DEFAULT_THRESHOLDS = (20.0, 30.0, 40.0, 50.0)


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable challenger command-line contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--profile-fingerprint")
    parser.add_argument(
        "--thresholds-bps", nargs="+", type=float, default=_DEFAULT_THRESHOLDS
    )
    parser.add_argument("--persistence-decisions", type=int, default=5)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def publish(args: argparse.Namespace) -> tuple[dict[str, object], Path]:
    """Snapshot active ledgers and publish one immutable evidence artifact."""
    output = _path(args.out, "challenger output")
    if output.exists():
        raise FileExistsError(f"immutable challenger output exists: {output}")
    ledger_root = _path(args.ledger_root, "ledger root")
    with ExitStack() as stack:
        cohort, assets, evidence = _snapshot_ledgers(
            stack, ledger_root, _text(args.run_id, "run id")
        )
        audit = audit_multi_asset_live_run(cohort, assets, run_id=args.run_id)
        report = _build_report(args, audit, cohort, assets)
    report["evidence"] = evidence
    write_immutable_json(output, report)
    return report, output


def _snapshot_ledgers(
    stack: ExitStack, ledger_root: Path, run_id: str
) -> tuple[
    list[dict[str, object]],
    dict[str, list[dict[str, object]]],
    dict[str, object],
]:
    cohort_path = ledger_root / "decisions.jsonl"
    cohort, cohort_facts = stack.enter_context(
        snapshot_decision_ledger(cohort_path, allow_incomplete_tail=True)
    )
    _, identity = select_armed_live_run(cohort, run_id)
    asset_paths = _asset_paths(ledger_root, cohort_path, configured_symbols(identity))
    assets: dict[str, list[dict[str, object]]] = {}
    asset_facts: dict[str, object] = {}
    for symbol, path in asset_paths.items():
        rows, facts = stack.enter_context(
            snapshot_decision_ledger(path, allow_incomplete_tail=True)
        )
        assets[symbol] = rows
        asset_facts[symbol] = _evidence(path, rows, facts)
    evidence = {
        "cohort": _evidence(cohort_path, cohort, cohort_facts),
        "assets": asset_facts,
    }
    return cohort, assets, evidence


def _build_report(
    args: argparse.Namespace,
    audit: Record,
    cohort: Sequence[Record],
    assets: Mapping[str, Sequence[Record]],
) -> dict[str, object]:
    trade_reflections = _mapping(audit.get("trade_reflections"), "reflections")
    all_time = _mapping(trade_reflections.get("all_time_live"), "all-time trades")
    open_reflections = _mapping(audit.get("open_trade_reflections"), "open trades")
    profile = args.profile_fingerprint or _audit_profile(audit)
    return build_regime_loss_exit_challenger(
        cohort,
        assets,
        closed_trades=_records(all_time.get("trades"), "closed trades"),
        open_trades=_records(open_reflections.get("trades"), "open trades"),
        current_run_id=_text(args.run_id, "run id"),
        current_profile_fingerprint=_text(profile, "profile fingerprint"),
        thresholds_bps=tuple(args.thresholds_bps),
        persistence_decisions=args.persistence_decisions,
    )


def _asset_paths(
    ledger_root: Path, cohort_path: Path, symbols: Sequence[str]
) -> dict[str, Path]:
    available = {
        path.stem.casefold(): path
        for path in sorted(ledger_root.glob("*.jsonl"))
        if path != cohort_path
    }
    if len(available) != len(list(ledger_root.glob("*.jsonl"))) - 1:
        raise ValueError("asset ledger names collide case-insensitively")
    missing = [symbol for symbol in symbols if symbol.casefold() not in available]
    if missing:
        raise FileNotFoundError(f"configured asset ledgers missing: {missing}")
    return {symbol: available[symbol.casefold()] for symbol in symbols}


def _audit_profile(audit: Record) -> str:
    run = _mapping(audit.get("run"), "audit run")
    return _text(run.get("profile_fingerprint"), "audit profile fingerprint")


def _evidence(
    path: Path, rows: Sequence[Record], facts: Mapping[str, object]
) -> dict[str, object]:
    return {"path": str(path), "complete_rows": len(rows), **facts}


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _records(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
        raise TypeError(f"{label} must be a list of mappings")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _path(value: object, label: str) -> Path:
    if not isinstance(value, Path):
        raise TypeError(f"{label} must be a path")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Run once and print a bounded operational summary."""
    report, output = publish(build_parser().parse_args(argv))
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(output),
                "closed_lifecycles": len(report["closed_lifecycles"]),
                "open_lifecycles": len(report["open_lifecycles"]),
                "execution_authority": "none",
                "runtime_strategy_changed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
