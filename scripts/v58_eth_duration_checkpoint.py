#!/usr/bin/env python3
"""Publish immutable point-in-time V58 ETH duration checkpoint evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.v58_eth_duration_checkpoint import (
    load_v58_eth_duration_checkpoint_report,
)

_STATUS = Path("data/runtime/research/v58_eth_pullback_first_lifecycle_latest.json")


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only V58 ETH duration checkpoint parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=Path, default=_STATUS)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def publish_report(args: argparse.Namespace) -> dict[str, object]:
    """Publish one source-bound authority-none duration report."""
    report = load_v58_eth_duration_checkpoint_report(args.status)
    write_immutable_json(args.out, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Run the immutable report-only publisher."""
    args = build_parser().parse_args(argv)
    try:
        report = publish_report(args)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"V58 ETH duration checkpoint failed: {exc}", file=sys.stderr)
        return 2
    payload = {
        "out": str(args.out),
        "mode": report.get("mode"),
        "execution_authority": report.get("execution_authority"),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
