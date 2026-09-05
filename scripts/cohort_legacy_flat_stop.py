#!/usr/bin/env python3
"""Stop one exact legacy cohort immediately after its next clean flat snapshot."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from hypervector.live.cohort_legacy_flat_stop import (
    LegacyFlatStopError,
    load_existing_final_flat_boundary,
    watch_legacy_flat_boundary,
    write_legacy_stop_request,
)
from hypervector.runtime_lock import RuntimeLockError, bidirectional_live_runtime_lock


def build_parser() -> argparse.ArgumentParser:
    """Build an exact-run, report-only-by-default watcher command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--expected-profile-fingerprint", required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument(
        "--expected-symbol",
        action="append",
        required=True,
        help="repeat once for every exact cohort asset",
    )
    parser.add_argument("--poll-seconds", type=float, default=0.1)
    parser.add_argument("--timeout-seconds", type=float)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write-stop",
        action="store_true",
        help="exclusively create STOP after the exact boundary is observed",
    )
    mode.add_argument(
        "--archive-existing-final-snapshot",
        type=Path,
        help="archive the latest exact final snapshot while the account lock is free",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    """Observe the next exact boundary and optionally request a clean stop."""
    if args.archive_existing_final_snapshot is not None:
        with bidirectional_live_runtime_lock(args.ledger):
            evidence = load_existing_final_flat_boundary(
                args.ledger,
                expected_profile_fingerprint=str(args.expected_profile_fingerprint),
                expected_run_id=str(args.expected_run_id),
                expected_symbols=tuple(args.expected_symbol),
            )
            write_legacy_stop_request(args.archive_existing_final_snapshot, evidence)
    else:
        evidence = watch_legacy_flat_boundary(
            args.ledger,
            expected_profile_fingerprint=str(args.expected_profile_fingerprint),
            expected_run_id=str(args.expected_run_id),
            expected_symbols=tuple(args.expected_symbol),
            poll_seconds=float(args.poll_seconds),
            timeout_seconds=args.timeout_seconds,
        )
    if args.write_stop and args.archive_existing_final_snapshot is None:
        write_legacy_stop_request(args.stop_file, evidence)
    archived = args.archive_existing_final_snapshot is not None
    print(
        json.dumps(
            {
                "ok": True,
                "status": (
                    "final_snapshot_archived"
                    if archived
                    else "stop_requested"
                    if args.write_stop
                    else "flat_boundary_observed"
                ),
                "stop_written": bool(args.write_stop),
                "archive_written": archived,
                "execution_authority": "none",
                "automatic_order_action": False,
                "evidence": asdict(evidence),
            },
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    """Report a concise refusal without weakening the exact-run contract."""
    try:
        return run(build_parser().parse_args())
    except (LegacyFlatStopError, RuntimeLockError) as exc:
        print(f"legacy flat-stop watcher refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
