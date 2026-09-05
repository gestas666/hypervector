#!/usr/bin/env python3
"""Publish one immutable report-only HYPE-native exact-depth path."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from hashlib import sha256
import json
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.hype_native_counterfactual_paths import (
    HypeNativePathSpec,
    build_hype_native_counterfactual_path,
)
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger

_GENERATOR_FILES = tuple(
    Path(value).resolve()
    for value in (
        __file__,
        "src/hypervector/research/hype_native_counterfactual_paths.py",
        "src/hypervector/research/cohort_exact_depth_books.py",
        "src/hypervector/research/cohort_signal_candidates.py",
        "src/hypervector/research/market_depth_fill.py",
        "src/hypervector/research/live_ledger_snapshot.py",
        "src/hypervector/data/oxa_storage.py",
    )
)


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable exact-depth path parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--asset-ledger", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--profile-fingerprint", required=True)
    parser.add_argument("--source-strategy-id", required=True)
    parser.add_argument("--candidate-strategy-id", required=True)
    parser.add_argument("--side", choices=("long", "short"), required=True)
    parser.add_argument("--decision-time-ms", type=int, required=True)
    parser.add_argument("--notional-usd", type=float, required=True)
    parser.add_argument("--stop-bps", type=float, required=True)
    parser.add_argument("--maximum-entry-delay-ms", type=int, required=True)
    parser.add_argument("--maximum-exit-delay-ms", type=int, required=True)
    parser.add_argument("--soft-hold-seconds", type=int, required=True)
    parser.add_argument("--hard-hold-seconds", type=int, required=True)
    parser.add_argument("--fee-bps-per-side", type=float, required=True)
    parser.add_argument("--residual-slippage-bps-per-side", type=float, required=True)
    parser.add_argument("--maximum-clock-skew-ms", type=int, required=True)
    parser.add_argument("--horizons-minutes", required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def publish_path(args: argparse.Namespace) -> dict[str, object]:
    """Freeze both active ledgers and publish one immutable path report."""
    if args.out.exists():
        raise FileExistsError(f"HYPE-native path output exists: {args.out}")
    generator = _generator_identity()
    with snapshot_decision_ledger(args.decisions, run_id=args.run_id) as cohort:
        with snapshot_decision_ledger(args.asset_ledger, run_id=args.run_id) as asset:
            report = build_hype_native_counterfactual_path(
                cohort[0], asset[0], _spec(args)
            )
    report["evidence"] = {
        "cohort_ledger": {"path": str(args.decisions), **cohort[1]},
        "asset_ledger": {"path": str(args.asset_ledger), **asset[1]},
    }
    report["generator_identity"] = {"files": generator}
    if generator != _generator_identity():
        raise RuntimeError("HYPE-native path generator changed during evaluation")
    write_immutable_json(args.out, report)
    return report


def _spec(args: argparse.Namespace) -> HypeNativePathSpec:
    return HypeNativePathSpec(
        run_id=args.run_id,
        profile_id=args.profile_id,
        profile_fingerprint=args.profile_fingerprint,
        source_strategy_id=args.source_strategy_id,
        candidate_strategy_id=args.candidate_strategy_id,
        symbol="HYPE",
        side=args.side,
        decision_time_ms=args.decision_time_ms,
        notional_usd=args.notional_usd,
        stop_bps=args.stop_bps,
        maximum_entry_delay_ms=args.maximum_entry_delay_ms,
        maximum_exit_delay_ms=args.maximum_exit_delay_ms,
        soft_hold_seconds=args.soft_hold_seconds,
        hard_hold_seconds=args.hard_hold_seconds,
        fee_bps_per_side=args.fee_bps_per_side,
        residual_slippage_bps_per_side=args.residual_slippage_bps_per_side,
        maximum_clock_skew_ms=args.maximum_clock_skew_ms,
        horizons_minutes=_horizons(args.horizons_minutes),
    )


def _horizons(value: str) -> tuple[int, ...]:
    try:
        horizons = tuple(int(item.strip()) for item in value.split(","))
    except ValueError as error:
        raise ValueError(
            "HYPE-native horizons must be comma-separated integers"
        ) from error
    if not horizons or any(item <= 0 for item in horizons):
        raise ValueError("HYPE-native horizons must be positive")
    if len(set(horizons)) != len(horizons):
        raise ValueError("HYPE-native horizons must be unique")
    return horizons


def _generator_identity() -> list[dict[str, object]]:
    return [_file_record(path) for path in _GENERATOR_FILES]


def _file_record(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {"path": str(path), "sha256": sha256(raw).hexdigest(), "bytes": len(raw)}


def main(argv: Sequence[str] | None = None) -> int:
    """Publish a report without constructing an exchange client."""
    report = publish_path(build_parser().parse_args(argv))
    print(
        json.dumps(
            {
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
