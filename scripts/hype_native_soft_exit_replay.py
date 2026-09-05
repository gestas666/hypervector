#!/usr/bin/env python3
"""Replay one restored-HYPE soft deadline with no execution authority."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.hype_native_soft_exit_replay import (
    build_hype_native_soft_exit_report,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded report-only command surface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--opened-at-ms", type=int, required=True)
    parser.add_argument("--observed-ms", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Build and publish one immutable counterfactual policy decision."""
    args = build_parser().parse_args(argv)
    report = build_hype_native_soft_exit_report(
        config_path=args.config,
        ledger_path=args.ledger,
        opened_at_ms=args.opened_at_ms,
        observed_ms=args.observed_ms,
    )
    write_immutable_json(args.out, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
