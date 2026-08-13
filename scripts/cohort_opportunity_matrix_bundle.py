#!/usr/bin/env python3
"""Continuously bundle report-only opportunity observers for the TUI."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import sys
import time

from hypervector.research.cohort_opportunity_matrix_bundle import (
    publish_opportunity_matrix_bundle,
)

PublishFn = Callable[[Path, Sequence[Path], Path], dict[str, object]]


class DestinationWriterActiveError(RuntimeError):
    """Raised when another process owns a rolling bundle destination."""


@contextmanager
def destination_lock(destination: Path) -> Iterator[None]:
    """Hold an advisory single-writer lock for one resolved destination."""
    resolved = destination.resolve()
    lock_path = resolved.with_name(f"{resolved.name}.writer.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise DestinationWriterActiveError(
                f"destination already has an active writer: {resolved}"
            ) from exc
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(f"pid={os.getpid()}\n")
        lock_file.flush()
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable local evidence bundler CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument(
        "--supplemental",
        action="append",
        type=Path,
        required=True,
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--once", action="store_true")
    return parser


def run_bundle_loop(
    args: argparse.Namespace,
    *,
    publish_fn: PublishFn = publish_opportunity_matrix_bundle,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Publish validated local evidence until stopped, preserving last good output."""
    if args.interval_seconds <= 0.0:
        raise ValueError("bundle interval must be positive")
    supplemental = tuple(args.supplemental)
    while True:
        try:
            bundled = publish_fn(args.primary, supplemental, args.out)
        except (OSError, UnicodeError, ValueError) as exc:
            _emit_unavailable(exc)
            if args.once:
                return 2
        else:
            _emit_success(bundled)
            if args.once:
                return 0
        sleep_fn(args.interval_seconds)


def _emit_success(bundled: dict[str, object]) -> None:
    challengers = bundled.get("supplemental_forward_challengers", [])
    count = len(challengers) if isinstance(challengers, list) else 0
    print(
        json.dumps(
            {
                "event": "cohort_opportunity_matrix_bundle",
                "execution_authority": "none",
                "state": "published",
                "supplemental_challengers": count,
            },
            sort_keys=True,
        ),
        flush=True,
    )


def _emit_unavailable(exc: Exception) -> None:
    print(
        json.dumps(
            {
                "event": "cohort_opportunity_matrix_bundle",
                "execution_authority": "none",
                "state": "unavailable",
                "technical_issue": f"{type(exc).__name__}: {exc}",
            },
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )


def main() -> int:
    """Run the local evidence bundler."""
    args = build_parser().parse_args()
    try:
        with destination_lock(args.out):
            return run_bundle_loop(args)
    except DestinationWriterActiveError as exc:
        _emit_unavailable(exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
