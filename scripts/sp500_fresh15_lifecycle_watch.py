#!/usr/bin/env python3
"""Continuously publish the authority-none first SP500 lifecycle status."""

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
from hypervector.research.sp500_fresh15_lifecycle_watch import (
    build_sp500_fresh15_lifecycle_status,
)
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock

ClockMs = Callable[[], int]
SleepFn = Callable[[float], None]
Record = dict[str, object]

_ROOT = Path(__file__).resolve().parents[1]
_GENERATOR_PATHS = (
    Path(__file__).resolve(),
    _ROOT / "src/hypervector/research/sp500_fresh15_lifecycle_watch.py",
    _ROOT / "src/hypervector/cohort_profit_lock_policy.py",
    _ROOT / "src/hypervector/live/multi_asset_market_bars.py",
    _ROOT / "src/hypervector/data/jsonl_prefix.py",
)


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable SP500 lifecycle watcher parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--preregistration-sha256", required=True)
    parser.add_argument("--decision-journal", type=Path, required=True)
    parser.add_argument("--profit-lock-candles", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=float, default=120.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    return parser


def watch_once(
    args: argparse.Namespace,
    *,
    clock_ms: ClockMs | None = None,
) -> Record:
    """Publish one exact, source-bound, authority-none lifecycle status."""
    preregistration_evidence = file_evidence(args.preregistration)
    _require_preregistration_hash(preregistration_evidence, args.preregistration_sha256)
    preregistration = _json_object(args.preregistration)
    decisions, decision_evidence = read_jsonl_prefix(
        args.decision_journal, "SP500 decision journal"
    )
    candles, candle_evidence = read_jsonl_prefix(
        args.profit_lock_candles, "SP500 profit-lock candle journal"
    )
    status = build_sp500_fresh15_lifecycle_status(
        preregistration,
        decisions,
        candles,
        observed_at_ms=(clock_ms or _current_time_ms)(),
    )
    generator = _generator_identity()
    payload = _payload(
        status,
        args,
        preregistration_evidence,
        decision_evidence,
        candle_evidence,
        generator,
    )
    _require_unchanged(
        args,
        preregistration_evidence,
        decision_evidence,
        candle_evidence,
        generator,
    )
    _require_safe(payload)
    write_atomic_json(args.status, payload)
    return payload


def run_watcher(
    args: argparse.Namespace,
    *,
    sleep_fn: SleepFn = time.sleep,
    clock_ms: ClockMs | None = None,
) -> int:
    """Refresh lifecycle status until interrupted or bounded completion."""
    _validate_runtime(args)
    cycles = 0
    while True:
        watch_once(args, clock_ms=clock_ms)
        cycles += 1
        if args.max_cycles and cycles >= args.max_cycles:
            return 0
        sleep_fn(args.interval_seconds)


def _payload(
    status: Mapping[str, object],
    args: argparse.Namespace,
    preregistration: Mapping[str, object],
    decisions: Mapping[str, object],
    candles: Mapping[str, object],
    generator: Mapping[str, object],
) -> Record:
    return {
        **dict(status),
        "input_evidence": {
            "preregistration": _path_evidence(args.preregistration, preregistration),
            "decision_journal_prefix": dict(decisions),
            "profit_lock_candle_prefix": dict(candles),
        },
        "generator_identity": dict(generator),
    }


def _require_unchanged(
    args: argparse.Namespace,
    preregistration: Mapping[str, object],
    decisions: Mapping[str, object],
    candles: Mapping[str, object],
    generator: Mapping[str, object],
) -> None:
    if file_evidence(args.preregistration) != dict(preregistration):
        raise ValueError("SP500 lifecycle preregistration changed during status build")
    require_jsonl_prefix_unchanged(
        args.decision_journal, decisions, "SP500 decision journal"
    )
    require_jsonl_prefix_unchanged(
        args.profit_lock_candles,
        candles,
        "SP500 profit-lock candle journal",
    )
    if _generator_identity() != dict(generator):
        raise ValueError("SP500 lifecycle watcher changed during status build")


def _require_preregistration_hash(
    evidence: Mapping[str, object], expected: object
) -> None:
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError("SP500 lifecycle preregistration hash must be exact SHA-256")
    if evidence.get("sha256") != expected:
        raise ValueError("SP500 lifecycle preregistration hash does not match")


def _validate_runtime(args: argparse.Namespace) -> None:
    interval = args.interval_seconds
    if not isinstance(interval, (int, float)) or not math.isfinite(interval):
        raise ValueError("SP500 lifecycle interval must be finite")
    if interval <= 0.0:
        raise ValueError("SP500 lifecycle interval must be positive")
    cycles = args.max_cycles
    if isinstance(cycles, bool) or not isinstance(cycles, int) or cycles < 0:
        raise ValueError("SP500 lifecycle max cycles must be nonnegative")


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
        raise ValueError("SP500 lifecycle watcher authority is invalid")


def _generator_identity() -> Record:
    return {
        "files": [
            {"path": str(path), **file_evidence(path)} for path in _GENERATOR_PATHS
        ]
    }


def _json_object(path: Path) -> Record:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("SP500 lifecycle preregistration must be an object")
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
