#!/usr/bin/env python3
"""Publish immutable BBO replay evidence for one fixed cohort near-miss contract."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from contextlib import ExitStack
import json
from pathlib import Path

from hypervector.data.hl import hl_coin
from hypervector.data.hl_funding_evidence import read_complete_hl_funding_evidence
from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.cohort_one_blocker_execution_feasibility import (
    OneBlockerExecutionContract,
    build_one_blocker_execution_feasibility,
)
from hypervector.research.cohort_live_audit_values import run_id
from hypervector.research.cohort_live_run_selection import select_armed_live_run
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay one exact-one-blocker hypothesis against recorded BBO."
    )
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--funding", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--strategy-id", default="range_onset_bidirectional_v1")
    parser.add_argument("--symbol", default="BTC")
    parser.add_argument("--blocker", default="awaiting_hourly_sma_cross")
    parser.add_argument("--horizon-minutes", type=int, default=60)
    parser.add_argument("--maximum-context-age-ms", type=int, default=30_000)
    parser.add_argument("--maximum-entry-delay-ms", type=int, default=60_000)
    parser.add_argument("--maximum-exit-delay-ms", type=int, default=30_000)
    parser.add_argument("--notional-usd", type=float, default=25.0)
    parser.add_argument("--taker-fee-rate", type=float, default=0.000432)
    parser.add_argument("--stop-proxy-bps", type=float, default=60.0)
    parser.add_argument(
        "--opi-cohort",
        choices=("aligned", "opposed", "all"),
        default="aligned",
    )
    return parser


def _publish(args: argparse.Namespace) -> tuple[dict[str, object], Path]:
    symbol = _normalized_symbol(args.symbol)
    cohort_path = args.ledger_root / "decisions.jsonl"
    asset_path = args.ledger_root / f"{symbol.lower()}.jsonl"
    if not args.funding.is_file():
        raise FileNotFoundError(f"funding evidence does not exist: {args.funding}")
    with ExitStack() as stack:
        cohort, cohort_evidence = stack.enter_context(
            snapshot_decision_ledger(cohort_path)
        )
        asset, asset_evidence = stack.enter_context(
            snapshot_decision_ledger(asset_path)
        )
        funding = read_complete_hl_funding_evidence(args.funding, symbol)
        selected, identity = select_armed_live_run(cohort, args.run_id)
        report = build_one_blocker_execution_feasibility(
            selected,
            {symbol: asset},
            funding.rows,
            contract=_contract(args, symbol),
        )
        executions = report.get("executions")
        if not isinstance(executions, list):
            raise ValueError("execution feasibility report has invalid executions")
        for execution in executions:
            if not isinstance(execution, dict):
                raise ValueError("execution feasibility row must be an object")
            funding.require_covers(
                int(execution["entry_time_ms"]), int(execution["exit_time_ms"])
            )
    report["evidence"] = {
        "cohort": {
            "path": str(cohort_path),
            "selected_run_id": run_id(identity),
            **cohort_evidence,
        },
        "asset": {"path": str(asset_path), **asset_evidence},
        "funding": funding.evidence,
    }
    if args.out.exists():
        raise FileExistsError(f"immutable feasibility output exists: {args.out}")
    write_immutable_json(args.out, report)
    return report, args.out


def _normalized_symbol(symbol: str) -> str:
    return hl_coin(symbol)


def _contract(args: argparse.Namespace, symbol: str) -> OneBlockerExecutionContract:
    return OneBlockerExecutionContract(
        strategy_id=args.strategy_id,
        symbol=symbol,
        blocker=args.blocker,
        horizon_minutes=args.horizon_minutes,
        maximum_context_age_ms=args.maximum_context_age_ms,
        maximum_entry_delay_ms=args.maximum_entry_delay_ms,
        maximum_exit_delay_ms=args.maximum_exit_delay_ms,
        notional_usd=args.notional_usd,
        taker_fee_rate=args.taker_fee_rate,
        stop_proxy_bps=args.stop_proxy_bps,
        opi_cohort=args.opi_cohort,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Publish quiet, unfavorable, incomplete, or favorable evidence unchanged."""
    report, output = _publish(_parser().parse_args(argv))
    print(
        json.dumps(
            {
                "out": str(output),
                "coverage": report["coverage"],
                "by_side": report["by_side"],
                "report_only": True,
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
