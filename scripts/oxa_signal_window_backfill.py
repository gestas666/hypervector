#!/usr/bin/env python3
"""Acquire and audit exact HYPE L2 windows around frozen labeled entries."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from hypervector.data.oxa_backfill import (
    OxaBackfillConfig,
    OxaBackfillResult,
    OxaBackfillTask,
    ProgressSink,
    run_oxa_tasks,
)
from hypervector.data.oxa_signal_windows import (
    OxaSignalWindow,
    OxaSignalWindowAudit,
    audit_signal_windows,
    load_signal_windows,
    tasks_for_signal_windows,
)
from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    write_immutable_json,
    write_json,
)
from hypervector.runtime_env import load_dotenv_if_present

_DEFAULT_FEATURES = Path(
    "data/logs/research/"
    "hype_breakout_entry_attribution_development_v2_20260804.features.parquet"
)
_DEFAULT_PLAN = Path("data/logs/research/hype_breakout_l2_signal_windows_plan_v1.json")
_DEFAULT_OUTPUT = Path("data/logs/research/hype_breakout_l2_signal_windows_audit_v1")


class TaskRunner(Protocol):
    """Callable boundary for the explicit resumable task pool."""

    def __call__(
        self,
        config: OxaBackfillConfig,
        *,
        tasks: tuple[OxaBackfillTask, ...],
        api_key: str,
        progress: ProgressSink,
    ) -> tuple[OxaBackfillResult, ...]: ...


@dataclass
class ProgressReporter:
    """Emit bounded JSON progress without exposing credentials."""

    expected: int
    every: int
    completed: int = 0
    downloaded: int = 0
    skipped: int = 0
    rows: int = 0

    def __post_init__(self) -> None:
        if self.expected < 1 or self.every < 1:
            raise ValueError("progress bounds must be positive")

    def __call__(self, result: OxaBackfillResult) -> None:
        self.completed += 1
        self.downloaded += int(not result.skipped)
        self.skipped += int(result.skipped)
        self.rows += result.rows
        if self.completed % self.every == 0 or self.completed == self.expected:
            print(json.dumps(self.payload(), sort_keys=True), flush=True)

    def payload(self) -> dict[str, object]:
        """Return the current bounded progress counters."""
        return {
            "event": "oxa_signal_window_progress",
            "completed": self.completed,
            "expected": self.expected,
            "downloaded": self.downloaded,
            "skipped": self.skipped,
            "rows": self.rows,
        }


def build_parser() -> argparse.ArgumentParser:
    """Build the full frozen HYPE signal-window acquisition command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=_DEFAULT_FEATURES)
    parser.add_argument("--symbol", default="HYPE")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--pre-seconds", type=int, default=60)
    parser.add_argument("--post-seconds", type=int, default=10)
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--book-max-pages", type=int, default=2)
    parser.add_argument("--maximum-pre-entry-age-ms", type=int, default=2_000)
    parser.add_argument("--maximum-post-entry-delay-ms", type=int, default=2_000)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--plan-out", type=Path, default=_DEFAULT_PLAN)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--plan-only", action="store_true")
    return parser


def run(
    args: argparse.Namespace,
    *,
    api_key: str,
    task_runner: TaskRunner = run_oxa_tasks,
) -> OxaSignalWindowAudit:
    """Publish a plan, acquire exact bundles, audit, and publish one bundle."""
    if not api_key.strip():
        raise ValueError("OXA_API_KEY is not configured")
    if args.out.exists():
        raise FileExistsError(f"immutable signal-window audit exists: {args.out}")
    windows, tasks, config = prepare(args)
    reporter = ProgressReporter(len(tasks), args.progress_every)
    results = task_runner(
        config,
        tasks=tasks,
        api_key=api_key,
        progress=reporter,
    )
    _validate_results(tasks, results)
    audit = audit_signal_windows(
        data_root=args.data_root,
        symbol=args.symbol,
        depth=args.depth,
        windows=windows,
        maximum_pre_entry_age_ms=args.maximum_pre_entry_age_ms,
        maximum_post_entry_delay_ms=args.maximum_post_entry_delay_ms,
    )
    _publish_audit_bundle(args, results, audit)
    return audit


def prepare(
    args: argparse.Namespace,
) -> tuple[
    tuple[OxaSignalWindow, ...],
    tuple[OxaBackfillTask, ...],
    OxaBackfillConfig,
]:
    """Load frozen labels and publish the exact request plan without network I/O."""
    windows = load_signal_windows(
        args.features,
        pre_seconds=args.pre_seconds,
        post_seconds=args.post_seconds,
    )
    tasks = tasks_for_signal_windows(windows)
    config = _backfill_config(args, windows)
    ensure_plan(args.plan_out, build_plan(args, windows))
    return windows, tasks, config


def build_plan(
    args: argparse.Namespace,
    windows: tuple[OxaSignalWindow, ...],
) -> dict[str, object]:
    """Build deterministic pre-request evidence for every targeted window."""
    requested_seconds = sum(
        (window.end - window.start).total_seconds() for window in windows
    )
    return {
        "schema_version": 1,
        "mode": "oxa_hype_signal_window_l2_plan",
        "contract": {
            "execution_authority": "none",
            "automatic_promotion": False,
            "strategy_mutation": False,
            "data_family": "hyperliquid_native_l2",
            "half_open_windows": True,
        },
        "source": {
            "feature_path": str(args.features.resolve()),
            "feature_file": file_evidence(args.features),
        },
        "request": {
            "symbol": args.symbol,
            "depth": args.depth,
            "pre_seconds": args.pre_seconds,
            "post_seconds": args.post_seconds,
            "book_max_pages": args.book_max_pages,
            "timeout_seconds": args.timeout_seconds,
        },
        "summary": {
            "signal_windows": len(windows),
            "aggregate_requested_seconds": requested_seconds,
            "earliest_start_utc": windows[0].start.isoformat(),
            "latest_end_utc": windows[-1].end.isoformat(),
        },
        "windows": [_window_payload(window) for window in windows],
    }


def ensure_plan(path: Path, payload: dict[str, object]) -> None:
    """Publish the immutable plan once or prove an exact resumable match."""
    if path.exists():
        observed = json.loads(path.read_text(encoding="utf-8"))
        if observed != payload:
            raise ValueError(f"existing signal-window plan differs: {path}")
        return
    write_immutable_json(path, payload)


def _backfill_config(
    args: argparse.Namespace,
    windows: tuple[OxaSignalWindow, ...],
) -> OxaBackfillConfig:
    return OxaBackfillConfig(
        symbol=args.symbol,
        start=windows[0].start,
        end=windows[-1].end,
        data_root=args.data_root,
        chunk=timedelta(seconds=args.pre_seconds + args.post_seconds),
        depth=args.depth,
        workers=args.workers,
        retries=args.retries,
        timeout_seconds=args.timeout_seconds,
        book_max_pages=args.book_max_pages,
    )


def _window_payload(window: OxaSignalWindow) -> dict[str, object]:
    return {
        "window_id": window.window_id,
        "side": window.side,
        "signal_time_utc": window.signal_time.isoformat(),
        "entry_time_utc": window.entry_time.isoformat(),
        "start_utc": window.start.isoformat(),
        "end_utc": window.end.isoformat(),
    }


def _validate_results(
    tasks: tuple[OxaBackfillTask, ...],
    results: tuple[OxaBackfillResult, ...],
) -> None:
    expected = {(task.kind, task.start, task.end) for task in tasks}
    observed = {
        (result.task.kind, result.task.start, result.task.end) for result in results
    }
    if observed != expected or len(results) != len(tasks):
        raise ValueError(
            "explicit backfill results do not cover the complete request plan"
        )


def _incomplete_message(audit: OxaSignalWindowAudit) -> str:
    statuses: dict[str, int] = {}
    for row in audit.rows:
        statuses[row.status] = statuses.get(row.status, 0) + 1
    return (
        "signal-window coverage incomplete: "
        f"bundles={audit.bundles_complete}/{audit.expected_signals} "
        f"causal={audit.causal_covered}/{audit.expected_signals} "
        f"execution={audit.execution_covered}/{audit.expected_signals} "
        f"statuses={json.dumps(statuses, sort_keys=True)}"
    )


def _publish_audit_bundle(
    args: argparse.Namespace,
    results: tuple[OxaBackfillResult, ...],
    audit: OxaSignalWindowAudit,
) -> None:
    def writer(staging: Path) -> None:
        index = staging / "index.parquet"
        audit.index_frame().to_parquet(index, index=False)
        report = {
            "schema_version": 1,
            "mode": "oxa_hype_signal_window_l2_audit",
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "coverage_complete": audit.complete,
            "contract": {
                "execution_authority": "none",
                "automatic_promotion": False,
                "strategy_mutation": False,
            },
            "evidence": {
                "plan_path": str(args.plan_out.resolve()),
                "plan": file_evidence(args.plan_out),
                "features_path": str(args.features.resolve()),
                "features": file_evidence(args.features),
                "index": file_evidence(index),
            },
            "acquisition": _result_summary(results),
            "coverage": audit.as_payload(),
        }
        write_json(staging / "audit.json", report)

    publish_immutable_directory(args.out, writer)


def _result_summary(results: tuple[OxaBackfillResult, ...]) -> dict[str, object]:
    return {
        "tasks": len(results),
        "downloaded": sum(not result.skipped for result in results),
        "resumed": sum(result.skipped for result in results),
        "rows": sum(result.rows for result in results),
        "pages": sum(result.pages for result in results),
    }


def main() -> int:
    """Load the local key, run the bounded job, and emit secret-free status."""
    args = build_parser().parse_args()
    try:
        if args.plan_only:
            windows, tasks, _ = prepare(args)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "plan_only": True,
                        "plan": str(args.plan_out),
                        "signals": len(windows),
                        "tasks": len(tasks),
                    },
                    sort_keys=True,
                )
            )
            return 0
        load_dotenv_if_present()
        audit = run(args, api_key=os.environ.get("OXA_API_KEY", ""))
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": audit.complete,
                "audit_published": True,
                "coverage_complete": audit.complete,
                "coverage_status": (
                    "complete" if audit.complete else _incomplete_message(audit)
                ),
                "output": str(args.out),
                "signals": audit.expected_signals,
                "rows": audit.total_rows,
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0 if audit.complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
