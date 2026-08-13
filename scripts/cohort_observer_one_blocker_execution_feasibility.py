#!/usr/bin/env python3
"""Publish immutable exact-depth replay evidence from a report-only observer."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
import json
from pathlib import Path

from hypervector.data.hl import hl_coin
from hypervector.data.hl_funding_evidence import (
    HlFundingEvidence,
    read_complete_hl_funding_evidence,
)
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.cohort_observer_exact_books import (
    extract_observer_asset_books,
    select_compatible_report_only_observer_runs,
    select_report_only_observer_run,
)
from hypervector.research.cohort_observer_depth_diagnostics import (
    build_attempt_entry_depth_diagnostics,
)
from hypervector.research.cohort_one_blocker_execution_contract import (
    OneBlockerExecutionContract,
)
from hypervector.research.cohort_one_blocker_execution_feasibility import (
    build_one_blocker_execution_feasibility,
)
from hypervector.research.cohort_live_audit_values import payload, run_id
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger

_GENERATOR_PATHS = (
    Path(__file__),
    Path("src/hypervector/research/cohort_observer_exact_books.py"),
    Path("src/hypervector/research/cohort_observer_depth_diagnostics.py"),
    Path("src/hypervector/research/cohort_one_blocker_execution_contract.py"),
    Path("src/hypervector/research/cohort_one_blocker_execution_feasibility.py"),
    Path("src/hypervector/research/cohort_one_blocker_execution_liquidity.py"),
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--funding", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--compatible-restarts", action="store_true")
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--blocker", required=True)
    parser.add_argument("--horizon-minutes", type=int, required=True)
    parser.add_argument("--notional-usd", type=float, required=True)
    parser.add_argument("--taker-fee-rate", type=float, required=True)
    parser.add_argument("--stop-proxy-bps", type=float, required=True)
    parser.add_argument("--maximum-context-age-ms", type=int, default=30_000)
    parser.add_argument("--maximum-entry-delay-ms", type=int, default=60_000)
    parser.add_argument("--maximum-exit-delay-ms", type=int, default=30_000)
    parser.add_argument("--minimum-available-time-ms", type=int, default=0)
    parser.add_argument("--minimum-entry-spacing-minutes", type=int)
    parser.add_argument("--target-proxy-bps", type=float)
    parser.add_argument(
        "--opi-cohort", choices=("aligned", "opposed", "all"), default="all"
    )
    parser.add_argument(
        "--liquidity-policy",
        choices=("top_level", "visible_depth"),
        default="visible_depth",
    )
    return parser


def _publish(args: argparse.Namespace) -> dict[str, object]:
    symbol = hl_coin(args.symbol)
    generator = _generator_evidence()
    with ExitStack() as stack:
        records, ledger_evidence = stack.enter_context(
            snapshot_decision_ledger(args.decisions, allow_incomplete_tail=True)
        )
        selected, identities = _selection(records, args)
        books = extract_observer_asset_books(selected, (symbol,))
        funding = read_complete_hl_funding_evidence(args.funding, symbol)
        replay = build_one_blocker_execution_feasibility(
            selected,
            books,
            funding.rows,
            contract=_contract(args, symbol),
        )
        _require_funding_coverage(replay, funding)
        depth = build_attempt_entry_depth_diagnostics(replay, books[symbol])
    if generator != _generator_evidence():
        raise RuntimeError("observer replay generator changed during evaluation")
    report = {
        **replay,
        "entry_depth_diagnostics": depth,
        "source": _source(args, identities, ledger_evidence, funding.evidence),
        "generator": generator,
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }
    write_immutable_json(args.out, report)
    return report


def _selection(
    records: Sequence[Mapping[str, object]], args: argparse.Namespace
) -> tuple[tuple[Mapping[str, object], ...], tuple[Mapping[str, object], ...]]:
    """Select one run or an explicitly anchored exact-contract continuation."""
    if args.compatible_restarts:
        if args.run_id is None:
            raise ValueError("compatible restart replay requires an origin run")
        return select_compatible_report_only_observer_runs(records, args.run_id)
    selected, identity = select_report_only_observer_run(records, args.run_id)
    return selected, (identity,)


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
        target_proxy_bps=args.target_proxy_bps,
        minimum_available_time_ms=args.minimum_available_time_ms,
        minimum_entry_spacing_minutes=args.minimum_entry_spacing_minutes,
        liquidity_policy=args.liquidity_policy,
    )


def _require_funding_coverage(
    report: Mapping[str, object], funding: HlFundingEvidence
) -> None:
    executions = report.get("executions")
    if not isinstance(executions, list):
        raise ValueError("observer replay executions must be a list")
    for row in executions:
        if not isinstance(row, Mapping):
            raise ValueError("observer replay execution must be an object")
        funding.require_covers(int(row["entry_time_ms"]), int(row["exit_time_ms"]))


def _source(
    args: argparse.Namespace,
    identities: Sequence[Mapping[str, object]],
    ledger: Mapping[str, object],
    funding: Mapping[str, object],
) -> dict[str, object]:
    if not identities:
        raise ValueError("observer replay requires a selected identity")
    identity = identities[0]
    values = payload(identity)
    return {
        "decisions": {"path": str(args.decisions), **ledger},
        "selected_run_id": run_id(identity),
        "compatible_run_ids": [run_id(row) for row in identities],
        "profile_id": identity.get("profile_id"),
        "effective_profile_fingerprint": identity.get("profile_fingerprint"),
        "base_config_source_path": values.get("config_source_path"),
        "funding": dict(funding),
    }


def _generator_evidence() -> dict[str, dict[str, object]]:
    return {str(path): file_evidence(path) for path in _GENERATOR_PATHS}


def main(argv: Sequence[str] | None = None) -> int:
    """Publish all valid outcomes, including sparse, losing, or unresolved rows."""
    args = _parser().parse_args(argv)
    report = _publish(args)
    print(
        json.dumps(
            {
                "out": str(args.out),
                "coverage": report["coverage"],
                "by_side": report["by_side"],
                "report_only": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
