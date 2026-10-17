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
from hypervector.runtime_lock import cohort_checkpoint_writer_active

# The paper observer ledger (paper observe's default ledger root) and the
# observer's own runtime directory: never the live ledger or live checkpoint.
_DEFAULT_DECISIONS = Path("data/paper/cohort/decisions.jsonl")
_DEFAULT_OUTPUT = Path("data/runtime/cohort_observer/latest_checkpoint.json")
EXIT_REFUSED = 2

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


def refuse_live_checkpoint_output(out: Path) -> str | None:
    """Name the conflict when a live checkpoint writer owns ``out``, else None."""
    if cohort_checkpoint_writer_active(out):
        return (
            f"{out} is owned by an active live checkpoint writer; choose an "
            "observer --out (default: data/runtime/cohort_observer/)"
        )
    return None


def main(argv: Sequence[str] | None = None) -> int:
    """Run a bounded setup-analysis sidecar with no execution authority."""
    args = build_parser().parse_args(argv)
    try:
        refusal = refuse_live_checkpoint_output(args.out)
        if refusal is not None:
            print(f"observer checkpoint refused: {refusal}", file=sys.stderr)
            return EXIT_REFUSED
        return run_checkpoint_loop(args)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError) as exc:
        print(f"observer checkpoint failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
