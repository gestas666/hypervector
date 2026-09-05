#!/usr/bin/env python3
"""Publish one immutable V86 ZEC UT-Bot peak-harvest partition report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.fixed_risk_signal_screen import utc_datetime
from hypervector.research.zec_utbot_peak_harvest_transfer import (
    run_partition_screen,
    run_short_partition_screen,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded execution-incapable partition command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--short-only", action="store_true")
    parser.add_argument(
        "--partition",
        required=True,
        choices=("development", "validation", "holdout"),
    )
    parser.add_argument("--bars", required=True, type=Path)
    parser.add_argument("--funding", required=True, type=Path, action="append")
    parser.add_argument("--source-start", required=True, type=utc_datetime)
    parser.add_argument("--score-start", required=True, type=utc_datetime)
    parser.add_argument("--end", required=True, type=utc_datetime)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one frozen partition and publish its immutable report."""
    args = build_parser().parse_args(argv)
    runner = run_short_partition_screen if args.short_only else run_partition_screen
    report = runner(
        bars_path=args.bars,
        funding_paths=args.funding,
        source_start=args.source_start,
        score_start=args.score_start,
        end=args.end,
        partition=args.partition,
    )
    write_immutable_json(args.output, report)
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "supported": report.get("supported_in_partition"),
                "status": "published",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
