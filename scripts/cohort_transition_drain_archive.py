#!/usr/bin/env python3
"""Archive completed cohort transition evidence after the backend stops."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
import sys

from hypervector.live.cohort_transition_drain import (
    CohortTransitionDrainError,
    archive_completed_transition_drain,
)
from hypervector.runtime_lock import RuntimeLockError, bidirectional_live_runtime_lock

_DEFAULT_STATE = Path("data/live/bidirectional_cohort/transition_drain.json")
_DEFAULT_ARCHIVE = Path("data/backups/bidirectional_cohort/transition_drains")
LockFn = Callable[[Path], AbstractContextManager[Path]]
NowFn = Callable[[], datetime]


def build_parser() -> argparse.ArgumentParser:
    """Build the dry-run-by-default archival command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=_DEFAULT_STATE)
    parser.add_argument("--archive-root", type=Path, default=_DEFAULT_ARCHIVE)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="archive verified evidence and clear the next-start blocker",
    )
    return parser


def run_archive(
    args: argparse.Namespace,
    *,
    lock_fn: LockFn = bidirectional_live_runtime_lock,
    now_fn: NowFn = lambda: datetime.now(UTC),
) -> Path:
    """Archive only while exclusive cohort runtime ownership is available."""
    state = Path(args.state)
    ledger = state.parent / "decisions.jsonl"
    with lock_fn(ledger):
        target = archive_completed_transition_drain(
            path=state,
            archive_root=Path(args.archive_root),
            expected_run_id=str(args.expected_run_id),
            now=now_fn(),
            confirmed=bool(args.yes),
        )
    action = "archived" if args.yes else "dry-run"
    print(f"transition drain {action}: source={state} destination={target}")
    return target


def main(argv: list[str] | None = None) -> int:
    """Return a nonzero status for active-runtime or evidence failures."""
    try:
        run_archive(build_parser().parse_args(argv))
    except (CohortTransitionDrainError, RuntimeLockError) as exc:
        print(f"transition drain archive refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
