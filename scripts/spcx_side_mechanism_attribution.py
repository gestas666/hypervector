#!/usr/bin/env python3
"""Publish exact report-only SPCX side and entry-timing attribution."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from hypervector.research.side_mechanism_attribution_command import (
    attribution_parser,
    print_attribution_summary,
    publish_attribution,
)
from hypervector.research.spcx_side_mechanism_attribution import (
    build_spcx_side_mechanism_attribution,
)

_SOURCE = Path(
    "data/logs/research/hip3_entry_timing_challenger_v3_20260809T134637Z.json"
)
_TRADES = Path(
    "data/logs/research/hip3_entry_timing_challenger_v3_20260809T134637Z.trades.parquet"
)
_STAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
_OUTPUT = Path(
    "data/logs/research/bidirectional_cohort/"
    f"spcx_side_mechanism_attribution_{_STAMP}.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Return the immutable report-only command parser."""
    return attribution_parser(
        __doc__ or "SPCX side-mechanism attribution",
        source=_SOURCE,
        trades=_TRADES,
        output=_OUTPUT,
    )


def run_command(args: argparse.Namespace) -> dict[str, object]:
    """Build and publish one source-bound immutable attribution artifact."""
    return publish_attribution(args, build_spcx_side_mechanism_attribution)


def main() -> int:
    """Run the attribution and print a bounded non-authoritative summary."""
    args = build_parser().parse_args()
    report = run_command(args)
    print_attribution_summary(args, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
