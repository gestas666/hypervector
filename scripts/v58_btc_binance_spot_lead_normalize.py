#!/usr/bin/env python3
"""Normalize the frozen Binance spot source without calculating outcomes."""

from __future__ import annotations

import argparse
from pathlib import Path

from hypervector.research.binance_spot_archive_normalization import (
    publish_normalized_binance_spot_bundle,
)


_BUNDLE_NAME = "20250728T000000Z_20260728T000000Z_spot_1m_v58_lead_v1"
_BUNDLE_ROOT = Path("data/cache/vendor/binance/BTCUSDT")


def build_parser() -> argparse.ArgumentParser:
    """Return the fixed-identity outcome-blind normalization parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=_BUNDLE_ROOT / _BUNDLE_NAME)
    parser.add_argument(
        "--output",
        type=Path,
        default=_BUNDLE_ROOT / f"{_BUNDLE_NAME}_normalized",
    )
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Publish the verified normalized source bundle."""
    return publish_normalized_binance_spot_bundle(args.source, args.output)


def main() -> int:
    """Normalize once and print the new immutable bundle path."""
    output = run_command(build_parser().parse_args())
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
