#!/usr/bin/env python3
"""Continuously publish exact v51 SOL one-blocker replay evidence."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from hypervector.runtime_lock import cohort_checkpoint_runtime_lock
from hypervector.research.sol_route_native_one_blocker_monitor import (
    SolRouteNativeMonitorSpec,
    run_sol_route_native_monitor,
)

_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
)
_COHORT_LEDGER = Path("data/live/bidirectional_cohort/decisions.jsonl")
_ASSET_LEDGER = Path("data/live/bidirectional_cohort/sol.jsonl")
_DATA_ROOT = Path("data")
_OUTPUT = Path(
    "data/runtime/bidirectional_cohort/"
    "latest_v51_sol_route_native_one_blocker_shadow.json"
)
_INTERVAL_SECONDS = 120.0
_ARCHIVE_LAG_SECONDS = 60.0


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable prospective observer parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--cohort-ledger", type=Path, default=_COHORT_LEDGER)
    parser.add_argument("--asset-ledger", type=Path, default=_ASSET_LEDGER)
    parser.add_argument("--data-root", type=Path, default=_DATA_ROOT)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--capture-start-ms", type=int, required=True)
    parser.add_argument("--out", type=Path, default=_OUTPUT)
    parser.add_argument("--interval-seconds", type=float, default=_INTERVAL_SECONDS)
    parser.add_argument(
        "--archive-lag-seconds", type=float, default=_ARCHIVE_LAG_SECONDS
    )
    parser.add_argument("--once", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one or continuous report-only refreshes for the frozen source run."""
    args = build_parser().parse_args(argv)
    spec = SolRouteNativeMonitorSpec(
        config_path=args.config,
        cohort_ledger=args.cohort_ledger,
        asset_ledger=args.asset_ledger,
        data_root=args.data_root,
        source_run_id=args.run_id,
        capture_start_ms=args.capture_start_ms,
        output=args.out,
    )
    with cohort_checkpoint_runtime_lock(spec.output):
        return run_sol_route_native_monitor(
            spec=spec,
            once=args.once,
            interval_seconds=args.interval_seconds,
            archive_lag_seconds=args.archive_lag_seconds,
        )


if __name__ == "__main__":
    raise SystemExit(main())
