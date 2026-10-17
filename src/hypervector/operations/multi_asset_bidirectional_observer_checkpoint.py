#!/usr/bin/env python3
"""Continuously publish bounded analysis for one disarmed observer ledger."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import time

from hypervector.research.cohort_observer_checkpoint import (
    publish_observer_checkpoint,
    publish_unavailable_observer_checkpoint,
)
from hypervector.runtime_lock import (
    RuntimeLockError,
    cohort_checkpoint_runtime_lock,
    cohort_checkpoint_writer_active,
)
from hypervector_supervision.cohort_supervisor_models import SupervisorPaths

# The paper observer ledger (paper observe's default ledger root) and the
# observer's own runtime directory: never the live ledger or live checkpoint.
_DEFAULT_DECISIONS = Path("data/paper/cohort/decisions.jsonl")
_DEFAULT_OUTPUT = Path("data/runtime/cohort_observer/latest_checkpoint.json")
# The live checkpoint's runtime directory under any data root
# (<data root>/runtime/bidirectional_cohort/), whatever the writer state.
_LIVE_RUNTIME_PARTS = ("runtime", "bidirectional_cohort")
_OBSERVER_MODE = "multi_asset_bidirectional_observer_checkpoint"
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
    """Publish until terminated, exposing incomplete startup evidence.

    The output is refused when it is the live checkpoint's directory, holds a
    document the observer did not write, or has an active writer. Otherwise the
    observer owns the output's writer lock for the whole loop, so a checkpoint
    writer that starts later cannot race a publication.
    """
    if args.interval_seconds <= 0.0:
        raise ValueError("checkpoint interval must be positive")
    refusal = refuse_live_checkpoint_output(args.out)
    if refusal is not None:
        print(f"observer checkpoint refused: {refusal}", file=sys.stderr)
        return EXIT_REFUSED
    with ExitStack() as owned:
        try:
            owned.enter_context(cohort_checkpoint_runtime_lock(args.out))
        except RuntimeLockError as exc:
            print(f"observer checkpoint refused: {exc}", file=sys.stderr)
            return EXIT_REFUSED
        return _publish_until_stopped(args, publish_fn=publish_fn, sleep_fn=sleep_fn)


def _publish_until_stopped(
    args: argparse.Namespace,
    *,
    publish_fn: PublishFn,
    sleep_fn: Callable[[float], None],
) -> int:
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
    """Name the conflict when ``out`` is or may be live output, else None.

    Refused whatever the writer state: any path in the live checkpoint's
    runtime directory, and an existing document the observer did not write
    (a live checkpoint at an unusual root, or anything unreadable). A held
    writer lock (a live checkpoint writer or another observer) is refused too.
    """
    hint = "choose an observer --out (default: data/runtime/cohort_observer/)"
    if _in_live_runtime_directory(out):
        return f"{out} is in the live checkpoint directory; {hint}"
    foreign = _foreign_document(out)
    if foreign is not None:
        return f"{out} holds {foreign}, not an observer checkpoint; {hint}"
    if cohort_checkpoint_writer_active(out):
        return (
            f"{out} is owned by an active live checkpoint writer or another "
            f"observer; {hint}"
        )
    return None


def _in_live_runtime_directory(out: Path) -> bool:
    directory = out.resolve().parent
    live = SupervisorPaths().checkpoint.parent.resolve()
    if directory == live or live in directory.parents:
        return True
    parts = directory.parts
    width = len(_LIVE_RUNTIME_PARTS)
    return any(
        parts[index : index + width] == _LIVE_RUNTIME_PARTS
        for index in range(len(parts) - width + 1)
    )


def _foreign_document(out: Path) -> str | None:
    """Describe an existing ``out`` the observer must not replace, else None."""
    if not out.exists():
        return None
    try:
        document = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return "an unreadable document"
    mode = document.get("mode") if isinstance(document, dict) else None
    if mode == _OBSERVER_MODE:
        return None
    return f"a {mode!r} document" if mode is not None else "a document without a mode"


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
