#!/usr/bin/env python3
"""Continuously publish bounded analysis for one disarmed observer ledger."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
import sys
import time

from hypervector.research.cohort_observer_checkpoint import (
    publish_observer_checkpoint,
    publish_unavailable_observer_checkpoint,
)

_DEFAULT_DECISIONS = Path("data/live/bidirectional_cohort/decisions.jsonl")
_DEFAULT_OUTPUT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")

PublishFn = Callable[..., dict[str, object]]


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable rolling observer CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=Path, default=_DEFAULT_DECISIONS)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--run-id")
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--once", action="store_true")
    return parser


def run_checkpoint_loop(
    args: argparse.Namespace,
    *,
    publish_fn: PublishFn = publish_observer_checkpoint,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Publish until terminated, exposing incomplete startup evidence."""
    if args.interval_seconds <= 0.0:
        raise ValueError("checkpoint interval must be positive")
    while True:
        try:
            publish_fn(args.decisions, args.out, run_id=args.run_id)
        except (FileNotFoundError, ValueError) as exc:
            publish_unavailable_observer_checkpoint(args.out, str(exc))
            print(f"observer checkpoint unavailable: {exc}", file=sys.stderr)
            if args.once:
                return 2
        else:
            if args.once:
                return 0
        sleep_fn(args.interval_seconds)


def main(argv: Sequence[str] | None = None) -> int:
    """Run a bounded setup-analysis sidecar with no execution authority."""
    try:
        return run_checkpoint_loop(build_parser().parse_args(argv))
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError) as exc:
        print(f"observer checkpoint failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
