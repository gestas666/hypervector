#!/usr/bin/env python3
"""Run the frozen HYPE breakout exit challenge on venue-matched history."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hype_breakout_exit_experiment import (
    build_breakout_entry_direction_comparison,
    build_hype_live_extension_comparison,
    build_hype_momentum_exit_comparison,
    run_hype_exit_experiment,
)
from hypervector.research.hype_breakout_alignment_experiment import (
    build_hype_breakout_alignment_comparison,
)
from hypervector.research.hype_breakout_exit_market import (
    build_hype_exit_market,
)

_DEFAULT_BARS = Path("data/cache/HYPE_1m_365d.parquet")
_DEFAULT_FUNDING = Path(
    "data/cache/vendor/hyperliquid/HYPE/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only HYPE exit experiment command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=_DEFAULT_BARS)
    parser.add_argument("--funding", type=Path, default=_DEFAULT_FUNDING)
    parser.add_argument("--holdout-days", type=int, default=60)
    parser.add_argument("--fold-count", type=int, default=5)
    comparison = parser.add_mutually_exclusive_group()
    comparison.add_argument("--compare-live-extension", action="store_true")
    comparison.add_argument("--compare-entry-direction", action="store_true")
    comparison.add_argument("--compare-entry-alignment", action="store_true")
    comparison.add_argument("--compare-momentum-exit", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Load authenticated local inputs and return the immutable report payload."""
    _require_file(args.bars, "HYPE bars")
    _require_file(args.funding, "HYPE funding")
    raw_bars = pd.read_parquet(args.bars)
    funding = pd.read_parquet(args.funding)
    market, market_evidence = build_hype_exit_market(raw_bars, funding)
    if args.compare_momentum_exit:
        report = build_hype_momentum_exit_comparison(
            market,
            holdout_days=args.holdout_days,
        )
    elif args.compare_entry_alignment:
        report = build_hype_breakout_alignment_comparison(
            market,
            holdout_days=args.holdout_days,
        )
    elif args.compare_entry_direction:
        breakout_market, breakout_evidence = build_hype_exit_market(
            raw_bars,
            funding,
            entry_direction_mode="breakout",
        )
        report = build_breakout_entry_direction_comparison(
            market,
            breakout_market,
            holdout_days=args.holdout_days,
        )
    elif args.compare_live_extension:
        report = build_hype_live_extension_comparison(
            market,
            holdout_days=args.holdout_days,
        )
    else:
        report = run_hype_exit_experiment(
            market,
            holdout_days=args.holdout_days,
            fold_count=args.fold_count,
        )
    report["data_evidence"] = {
        "bars_path": str(args.bars.resolve()),
        "bars": file_evidence(args.bars),
        "funding_path": str(args.funding.resolve()),
        "funding": file_evidence(args.funding),
        "reconstructed_market": asdict(market_evidence),
    }
    if args.compare_entry_direction:
        report["data_evidence"]["breakout_direction_market"] = asdict(breakout_evidence)
    return report


def main() -> None:
    """Execute once and publish without replacing prior research evidence."""
    args = build_parser().parse_args()
    report = run(args)
    write_immutable_json(args.out, report)
    summary: dict[str, object] = {
        "ok": True,
        "out": str(args.out),
        "holdout_comparison": report["holdout_comparison"],
        "execution_authority": "none",
    }
    if (
        args.compare_live_extension
        or args.compare_entry_direction
        or args.compare_entry_alignment
        or args.compare_momentum_exit
    ):
        summary["development_comparison"] = report["development_comparison"]
    else:
        summary["selection"] = report["selection"]
    print(
        json.dumps(
            summary,
            sort_keys=True,
        )
    )


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} does not exist: {path}")


if __name__ == "__main__":
    main()
