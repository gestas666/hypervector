#!/usr/bin/env python3
"""Continuously publish authority-none MU independent-window readiness."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
import json
import math
from pathlib import Path
import sys
import time
from typing import cast

from hypervector.data.jsonl_prefix import (
    read_jsonl_prefix,
    require_jsonl_prefix_unchanged,
)
from hypervector.data.oxa_storage import file_evidence
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.mu_source_native_window_watch import (
    build_mu_source_native_window_status,
)
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock

ClockMs = Callable[[], int]
SleepFn = Callable[[float], None]
Record = dict[str, object]

_GENERATOR_PATHS = (
    Path(__file__).resolve(),
    Path(__file__).resolve().parents[1]
    / "src/hypervector/research/mu_source_native_window_watch.py",
)


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable MU window watcher parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--preregistration-sha256", required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=float, default=120.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    return parser


def watch_once(
    args: argparse.Namespace,
    *,
    clock_ms: ClockMs | None = None,
) -> Record:
    """Publish one source-bound readiness status from an append-only prefix."""
    preregistration_evidence = file_evidence(args.preregistration)
    _require_preregistration_hash(preregistration_evidence, args.preregistration_sha256)
    preregistration = _json_object(args.preregistration)
    rows, journal_evidence = read_jsonl_prefix(args.journal, "MU decision journal")
    status = build_mu_source_native_window_status(
        preregistration,
        rows,
        observed_at_ms=(clock_ms or _current_time_ms)(),
    )
    generator = _generator_identity()
    payload = {
        **status,
        "input_evidence": {
            "preregistration": _path_evidence(
                args.preregistration, preregistration_evidence
            ),
            "journal_prefix": journal_evidence,
        },
        "generator_identity": generator,
    }
    _require_unchanged(args, preregistration_evidence, journal_evidence, generator)
    _require_safe(payload)
    write_atomic_json(args.status, payload)
    return payload


def run_watcher(
    args: argparse.Namespace,
    *,
    sleep_fn: SleepFn = time.sleep,
    clock_ms: ClockMs | None = None,
) -> int:
    """Refresh readiness until interrupted or a bounded cycle count completes."""
    _validate_runtime(args)
    cycles = 0
    while True:
        watch_once(args, clock_ms=clock_ms)
        cycles += 1
        if args.max_cycles and cycles >= args.max_cycles:
            return 0
        sleep_fn(args.interval_seconds)


def _require_unchanged(
    args: argparse.Namespace,
    preregistration: Mapping[str, object],
    journal: Mapping[str, object],
    generator: Mapping[str, object],
) -> None:
    if file_evidence(args.preregistration) != dict(preregistration):
        raise ValueError("MU window preregistration changed during status build")
    require_jsonl_prefix_unchanged(args.journal, journal, "MU decision journal")
    if _generator_identity() != dict(generator):
        raise ValueError("MU window watcher changed during status build")


def _require_preregistration_hash(
    evidence: Mapping[str, object], expected: object
) -> None:
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError("MU window preregistration hash must be exact SHA-256")
    if evidence.get("sha256") != expected:
        raise ValueError("MU window preregistration hash does not match")


def _validate_runtime(args: argparse.Namespace) -> None:
    interval = args.interval_seconds
    if not isinstance(interval, (int, float)) or not math.isfinite(interval):
        raise ValueError("MU window interval must be finite")
    if interval <= 0.0:
        raise ValueError("MU window interval must be positive")
    cycles = args.max_cycles
    if isinstance(cycles, bool) or not isinstance(cycles, int) or cycles < 0:
        raise ValueError("MU window max cycles must be nonnegative")


def _require_safe(status: Mapping[str, object]) -> None:
    safe = (
        status.get("report_only") is True
        and status.get("execution_authority") == "none"
        and status.get("orders_supported") is False
        and status.get("signing_client_constructed") is False
        and status.get("automatic_promotion") is False
        and status.get("runtime_strategy_changed") is False
    )
    if not safe:
        raise ValueError("MU window watcher authority is invalid")


def _generator_identity() -> Record:
    return {
        "files": [
            {"path": str(path), **file_evidence(path)} for path in _GENERATOR_PATHS
        ]
    }


def _json_object(path: Path) -> Record:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("MU window preregistration must be an object")
    return cast(Record, value)


def _path_evidence(path: Path, evidence: Mapping[str, object]) -> Record:
    return {"path": str(path.resolve()), **dict(evidence)}


def _current_time_ms() -> int:
    return time.time_ns() // 1_000_000


def main(argv: Sequence[str] | None = None) -> int:
    """Run under a singleton status-path lock without execution authority."""
    args = build_parser().parse_args(argv)
    args.status.parent.mkdir(parents=True, exist_ok=True)
    try:
        with cohort_checkpoint_runtime_lock(args.status):
            return run_watcher(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
