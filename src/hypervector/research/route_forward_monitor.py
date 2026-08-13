"""Shared continuous monitor for report-only route-forward snapshots."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
import time

CycleFn = Callable[[Sequence[str]], int]
SleepFn = Callable[[float], None]
ChangeFn = Callable[[Path, Path], bool]
MaterialAppender = Callable[[Path, Mapping[str, object]], bool]


@dataclass(frozen=True)
class RouteForwardMonitorSpec:
    """Bind one monitor to exact tracker inputs and material journal."""

    label: str
    event: str
    tracker: Path
    checkpoint: Path
    journal: Path
    source_config: Path
    candidate_config: Path
    output: Path
    change_journal: Path
    change_recorder: ChangeFn


def build_route_monitor_parser(
    spec: RouteForwardMonitorSpec,
) -> argparse.ArgumentParser:
    """Build the exact versioned monitor parser."""
    parser = argparse.ArgumentParser(description=f"Continuously refresh {spec.label}")
    parser.add_argument("--checkpoint", type=Path, default=spec.checkpoint)
    parser.add_argument("--journal", type=Path, default=spec.journal)
    parser.add_argument("--source-config", type=Path, default=spec.source_config)
    parser.add_argument("--candidate-config", type=Path, default=spec.candidate_config)
    parser.add_argument("--out", type=Path, default=spec.output)
    parser.add_argument("--change-journal", type=Path, default=spec.change_journal)
    parser.add_argument("--interval-seconds", type=float, default=120.0)
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="stop after this many refreshes; zero runs until terminated",
    )
    parser.add_argument("--once", action="store_true")
    return parser


def route_tracker_command(
    spec: RouteForwardMonitorSpec, args: argparse.Namespace
) -> list[str]:
    """Return the exact identity-bound one-shot tracker command."""
    return [
        sys.executable,
        str(spec.tracker),
        "--checkpoint",
        str(args.checkpoint),
        "--journal",
        str(args.journal),
        "--source-config",
        str(args.source_config),
        "--candidate-config",
        str(args.candidate_config),
        "--out",
        str(args.out),
    ]


def run_route_monitor(
    spec: RouteForwardMonitorSpec,
    args: argparse.Namespace,
    *,
    run_cycle: CycleFn,
    sleep_fn: SleepFn,
    record_change: ChangeFn | None = None,
) -> int:
    """Refresh until terminated while retaining any failed-cycle status."""
    _validate_args(spec, args)
    command = route_tracker_command(spec, args)
    cycle = 0
    aggregate_exit = 0
    while True:
        cycle += 1
        exit_code = run_cycle(command)
        if exit_code != 0:
            aggregate_exit = exit_code
        elif record_change is not None:
            record_change(args.out, args.change_journal)
        _log_cycle(spec, cycle, exit_code, args.out)
        if args.once or (args.max_cycles and cycle >= args.max_cycles):
            return aggregate_exit
        sleep_fn(args.interval_seconds)


def route_monitor_main(
    spec: RouteForwardMonitorSpec, argv: Sequence[str] | None = None
) -> int:
    """Run a continuous versioned report-only tracker."""
    args = build_route_monitor_parser(spec).parse_args(argv)
    return run_route_monitor(
        spec,
        args,
        run_cycle=_run_cycle,
        sleep_fn=time.sleep,
        record_change=spec.change_recorder,
    )


def record_material_change(
    snapshot_path: Path,
    journal_path: Path,
    *,
    appender: MaterialAppender,
) -> bool:
    """Load one published snapshot before invoking a material appender."""
    value = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("route-forward snapshot must be an object")
    return appender(journal_path, value)


def _validate_args(spec: RouteForwardMonitorSpec, args: argparse.Namespace) -> None:
    if args.interval_seconds <= 0.0:
        raise ValueError(f"{spec.label} interval must be positive")
    if args.max_cycles < 0:
        raise ValueError(f"{spec.label} max cycles cannot be negative")


def _run_cycle(command: Sequence[str]) -> int:
    completed = subprocess.run(command, check=False)
    return completed.returncode


def _log_cycle(
    spec: RouteForwardMonitorSpec, cycle: int, exit_code: int, out: Path
) -> None:
    print(
        json.dumps(
            {
                "event": spec.event,
                "cycle": cycle,
                "status": "ok" if exit_code == 0 else "error",
                "exit_code": exit_code,
                "out": str(out),
                "execution_authority": "none",
            }
        ),
        flush=True,
    )
