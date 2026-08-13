#!/usr/bin/env python3
"""Publish immutable report-only BTC successor sizing and stop exposure."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.btc_specialist_successor_risk import (
    build_btc_specialist_successor_risk,
)

_PROFILE = Path("configs/multi_asset_bidirectional_btc_specialists_candidate_v43.toml")
_OUTPUT = Path(
    "data/logs/research/bidirectional_cohort/"
    "v43_btc_specialist_successor_risk_20260811_v1.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Build a mutation-incapable report command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=_PROFILE)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument(
        "--account-values-usd",
        type=float,
        nargs="+",
        default=[500.0, 5_000.0],
    )
    parser.add_argument("--taker-fee-bps-per-side", type=float, default=4.5)
    return parser


def run(args: argparse.Namespace) -> int:
    """Build and atomically publish one immutable evidence document."""
    report = build_btc_specialist_successor_risk(
        args.profile,
        account_values_usd=args.account_values_usd,
        taker_fee_bps_per_side=args.taker_fee_bps_per_side,
    )
    write_immutable_json(args.output, report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Return a bounded error without exposing a live execution surface."""
    try:
        return run(build_parser().parse_args(argv))
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"BTC successor risk evidence failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
