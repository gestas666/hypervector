#!/usr/bin/env python3
"""Continuously publish report-only BRENTOIL lifecycle status."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
from typing import Protocol, cast

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock

ReportBuilder = Callable[[argparse.Namespace, Path], dict[str, object]]
ClockMs = Callable[[], int]
SleepFn = Callable[[float], None]


class LifecycleBuilder(Protocol):
    """Exact no-publication lifecycle builder contract."""

    def __call__(
        self, args: argparse.Namespace, *, destination: Path
    ) -> dict[str, object]: ...


def _load_lifecycle_builder() -> LifecycleBuilder:
    path = Path(__file__).with_name("brentoil_oil_shock_lifecycle.py")
    spec = importlib.util.spec_from_file_location("brentoil_lifecycle_command", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("BRENTOIL lifecycle command is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    value = getattr(module, "build_report", None)
    if not callable(value):
        raise RuntimeError("BRENTOIL lifecycle builder is unavailable")
    return cast(LifecycleBuilder, value)


build_report = _load_lifecycle_builder()
_WATCHER_GENERATOR_FILES = (
    Path(__file__).resolve(),
    Path(__file__).with_name("brentoil_oil_shock_lifecycle.py").resolve(),
)


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable continuous lifecycle parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--candle-ledger", type=Path, required=True)
    parser.add_argument("--book-ledger", type=Path, required=True)
    parser.add_argument("--mark-data-root", type=Path, required=True)
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--live-canary", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    return parser


def watch_once(
    args: argparse.Namespace,
    *,
    report_builder: ReportBuilder | None = None,
    clock_ms: ClockMs | None = None,
) -> dict[str, object]:
    """Build and atomically publish one report-only lifecycle status."""
    builder = report_builder or _default_report_builder
    cycle = _cycle_args(args, (clock_ms or _current_time_ms)())
    report = builder(cycle, args.status)
    _require_safe(report)
    generator = _watcher_generator_identity()
    payload = {**report, "watcher_generator_identity": generator}
    state_id = _state_id(payload)
    snapshot = _snapshot(args, payload, state_id)
    technical = _mapping(report.get("technical_assessment"), "technical assessment")
    status = {
        **payload,
        "watch_state": technical.get("status"),
        "watch_state_id": state_id,
        "snapshot": snapshot,
    }
    if generator != _watcher_generator_identity():
        raise RuntimeError("BRENTOIL lifecycle watcher changed during evaluation")
    write_atomic_json(args.status, status)
    return status


def run_watcher(
    args: argparse.Namespace,
    *,
    report_builder: ReportBuilder | None = None,
    sleep_fn: SleepFn = time.sleep,
    clock_ms: ClockMs | None = None,
) -> int:
    """Refresh status continuously or stop after a bounded cycle count."""
    _validate_watch_args(args)
    cycles = 0
    clock = clock_ms or _current_time_ms
    while True:
        watch_once(args, report_builder=report_builder, clock_ms=clock)
        cycles += 1
        if args.max_cycles and cycles >= args.max_cycles:
            return 0
        sleep_fn(args.interval_seconds)


def _cycle_args(args: argparse.Namespace, observed_at_ms: int) -> argparse.Namespace:
    values = vars(args).copy()
    values["observed_at_ms"] = _positive_integer(observed_at_ms, "observed at")
    return argparse.Namespace(**values)


def _current_time_ms() -> int:
    return time.time_ns() // 1_000_000


def _validate_watch_args(args: argparse.Namespace) -> None:
    interval = args.interval_seconds
    if not isinstance(interval, (int, float)) or not math.isfinite(interval):
        raise ValueError("BRENTOIL lifecycle watch interval must be finite")
    if interval <= 0.0:
        raise ValueError("BRENTOIL lifecycle watch interval must be positive")
    maximum = args.max_cycles
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 0:
        raise ValueError("BRENTOIL lifecycle max cycles must be nonnegative")


def _default_report_builder(
    args: argparse.Namespace, destination: Path
) -> dict[str, object]:
    return build_report(args, destination=destination)


def _state_id(report: Mapping[str, object]) -> str:
    selected = {
        field: report.get(field)
        for field in (
            "technical_assessment",
            "source",
            "nominal",
            "stress",
            "watcher_generator_identity",
        )
    }
    raw = json.dumps(selected, sort_keys=True, separators=(",", ":")).encode()
    return sha256(raw).hexdigest()


def _watcher_generator_identity() -> dict[str, object]:
    files = [
        {"path": str(path), **file_evidence(path)} for path in _WATCHER_GENERATOR_FILES
    ]
    return {"files": files}


def _snapshot(
    args: argparse.Namespace, report: Mapping[str, object], state_id: str
) -> str | None:
    source = _mapping(report.get("source"), "source")
    eligible = _nonnegative_integer(source.get("eligible_decisions"), "eligible")
    if eligible == 0:
        return None
    nominal = _mapping(report.get("nominal"), "nominal")
    summary = _mapping(nominal.get("summary"), "nominal summary")
    resolved = _nonnegative_integer(summary.get("resolved"), "resolved")
    path = args.snapshot_dir / (
        f"brentoil_{eligible:04d}_{resolved:04d}_{state_id[:12]}.json"
    )
    payload = {**report, "watch_state_id": state_id}
    if path.exists():
        observed = json.loads(path.read_text(encoding="utf-8"))
        if observed != payload:
            raise ValueError("BRENTOIL lifecycle snapshot identity differs")
    else:
        write_immutable_json(path, payload)
    return str(path)


def _require_safe(report: Mapping[str, object]) -> None:
    technical = _mapping(report.get("technical_assessment"), "technical assessment")
    safe = (
        report.get("execution_authority") == "none"
        and report.get("report_only") is True
        and report.get("automatic_promotion") is False
        and report.get("runtime_strategy_changed") is False
        and technical.get("live_change_supported") is False
    )
    if not safe:
        raise ValueError("BRENTOIL lifecycle watcher report authority is invalid")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"BRENTOIL lifecycle watcher {label} must be an object")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"BRENTOIL lifecycle watcher {label} must be nonnegative")
    return value


def _positive_integer(value: object, label: str) -> int:
    output = _nonnegative_integer(value, label)
    if output == 0:
        raise ValueError(f"BRENTOIL lifecycle watcher {label} must be positive")
    return output


def main(argv: Sequence[str] | None = None) -> int:
    """Run the lifecycle watcher."""
    args = build_parser().parse_args(argv)
    args.status.parent.mkdir(parents=True, exist_ok=True)
    args.snapshot_dir.mkdir(parents=True, exist_ok=True)
    try:
        with cohort_checkpoint_runtime_lock(args.status):
            return run_watcher(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
