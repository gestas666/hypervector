#!/usr/bin/env python3
"""Publish immutable report-only V58 ETH historical funding stress."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.v58_eth_historical_funding_stress import (
    load_v58_eth_historical_funding_stress,
)

_BUNDLE = Path(
    "data/cache/vendor/hyperliquid/ETH/"
    "20250728T000000000000Z_20260728T000000000000Z_funding"
)
_STRESS = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_eight_asset_growth_sizing_stress_20260819_v1.json"
)
_CURRENT = Path("data/runtime/research/v58_continuous_improvement_latest.json")


def build_parser() -> argparse.ArgumentParser:
    """Build the source-bound historical funding diagnostic parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--funding", type=Path, default=_BUNDLE / "funding.parquet")
    parser.add_argument("--manifest", type=Path, default=_BUNDLE / "manifest.json")
    parser.add_argument("--stress", type=Path, default=_STRESS)
    parser.add_argument("--current-context", type=Path, default=_CURRENT)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def publish_report(args: argparse.Namespace) -> dict[str, object]:
    """Publish one immutable, authority-none historical funding report."""
    report = load_v58_eth_historical_funding_stress(
        funding_path=args.funding,
        manifest_path=args.manifest,
        stress_path=args.stress,
        current_context_path=args.current_context,
    )
    if report.get("execution_authority") != "none":
        raise ValueError("historical funding report has execution authority")
    if report.get("sizing_input") is not False:
        raise ValueError("historical funding report claims sizing authority")
    write_immutable_json(args.out, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Run the immutable report-only publisher."""
    args = build_parser().parse_args(argv)
    try:
        report = publish_report(args)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"V58 ETH historical funding stress failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "out": str(args.out),
                "mode": report.get("mode"),
                "execution_authority": report.get("execution_authority"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
