#!/usr/bin/env python3
"""Publish immutable stop-path evidence for one report-only near miss."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from hashlib import sha256
import json
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.cohort_nearmiss_stop_path import (
    NearMissPathSpec,
    build_nearmiss_stop_path,
)
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger

_GENERATOR_FILES = (
    Path(__file__).resolve(),
    Path("src/hypervector/research/cohort_nearmiss_stop_path.py").resolve(),
    Path("src/hypervector/research/cohort_nearmiss_stop_path_reporting.py").resolve(),
    Path("src/hypervector/research/live_ledger_snapshot.py").resolve(),
    Path("src/hypervector/data/oxa_storage.py").resolve(),
)


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable near-miss parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--asset-ledger", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--profile-fingerprint", required=True)
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--side", choices=("long", "short"), required=True)
    parser.add_argument("--decision-time-ms", type=int, required=True)
    parser.add_argument("--available-time-ms", type=int, required=True)
    parser.add_argument("--reference-price", type=float, required=True)
    parser.add_argument("--stop-bps", type=float, required=True)
    parser.add_argument("--target-bps", type=float)
    parser.add_argument("--soft-maximum-hold-seconds", type=int, required=True)
    parser.add_argument("--modeled-hurdle-bps", type=float, required=True)
    parser.add_argument("--notional-usd", type=float, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def publish_path(args: argparse.Namespace) -> dict[str, object]:
    """Snapshot both ledgers and publish one immutable causal path."""
    if args.out.exists():
        raise FileExistsError(f"near-miss output exists: {args.out}")
    generator = {"files": _generator_identity()}
    with snapshot_decision_ledger(args.decisions, run_id=args.run_id) as cohort:
        with snapshot_decision_ledger(args.asset_ledger, run_id=args.run_id) as asset:
            report = build_nearmiss_stop_path(cohort[0], asset[0], _spec(args))
    report["evidence"] = {
        "cohort_ledger": {"path": str(args.decisions), **cohort[1]},
        "asset_ledger": {"path": str(args.asset_ledger), **asset[1]},
    }
    report["generator_identity"] = generator
    if generator["files"] != _generator_identity():
        raise RuntimeError("near-miss generator changed during evaluation")
    write_immutable_json(args.out, report)
    return report


def _spec(args: argparse.Namespace) -> NearMissPathSpec:
    return NearMissPathSpec(
        run_id=args.run_id,
        profile_id=args.profile_id,
        profile_fingerprint=args.profile_fingerprint,
        strategy_id=args.strategy_id,
        symbol=args.symbol,
        side=args.side,
        decision_time_ms=args.decision_time_ms,
        available_time_ms=args.available_time_ms,
        reference_price=args.reference_price,
        stop_bps=args.stop_bps,
        soft_maximum_hold_seconds=args.soft_maximum_hold_seconds,
        modeled_round_trip_hurdle_bps=args.modeled_hurdle_bps,
        notional_usd=args.notional_usd,
        target_bps=args.target_bps,
    )


def _generator_identity() -> list[dict[str, object]]:
    return [_file_record(path) for path in _GENERATOR_FILES]


def _file_record(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {"path": str(path), "sha256": sha256(raw).hexdigest(), "bytes": len(raw)}


def main(argv: Sequence[str] | None = None) -> int:
    """Publish evidence without constructing an exchange client."""
    args = build_parser().parse_args(argv)
    report = publish_path(args)
    print(
        json.dumps(
            {
                "out": str(args.out),
                "status": report["status"],
                "report_only": True,
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
