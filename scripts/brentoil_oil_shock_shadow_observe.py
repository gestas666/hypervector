#!/usr/bin/env python3
"""Run the isolated unsigned BRENTOIL oil-shock shadow observer."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import signal
import threading
import time
from types import FrameType
from typing import Protocol

from hypervector.live.brentoil_oil_shock_shadow_runner import (
    BrentoilOilShockPublicRestSource,
    BrentoilOilShockShadowPaths,
    BrentoilOilShockShadowPollResult,
    BrentoilOilShockShadowRunner,
)
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock

_ROOT = Path("data/live/research/brentoil_oil_shock_shadow")
_RUNTIME = Path("data/runtime/research")


class _Runner(Protocol):
    def poll(self, *, observed_at_ms: int) -> BrentoilOilShockShadowPollResult:
        """Advance one report-only observation cycle."""


@dataclass(frozen=True)
class ObserverConfig:
    """Validated standalone polling and storage contract."""

    paths: BrentoilOilShockShadowPaths
    poll_seconds: float = 5.0
    max_polls: int | None = None
    execution_authority: str = "none"
    report_only: bool = True

    def __post_init__(self) -> None:
        """Reject invalid loops or any attempted authority escalation."""
        if self.poll_seconds <= 0.0:
            raise ValueError("BRENTOIL shadow poll_seconds must be positive")
        if self.max_polls is not None and self.max_polls <= 0:
            raise ValueError("BRENTOIL shadow max_polls must be positive")
        if self.execution_authority != "none" or self.report_only is not True:
            raise ValueError("BRENTOIL shadow observer must remain report-only")


def build_parser() -> argparse.ArgumentParser:
    """Build the public-data-only BRENTOIL observer parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-ledger", type=Path, default=_ROOT / "rest_books.jsonl")
    parser.add_argument("--candle-ledger", type=Path, default=_ROOT / "candles.jsonl")
    parser.add_argument(
        "--cursor",
        type=Path,
        default=_RUNTIME / "brentoil_oil_shock_shadow_cursor.json",
    )
    parser.add_argument("--journal", type=Path, default=_ROOT / "decisions.jsonl")
    parser.add_argument(
        "--status",
        type=Path,
        default=_RUNTIME / "brentoil_oil_shock_shadow_latest.json",
    )
    parser.add_argument("--websocket-archive", type=Path, default=_ROOT / "ws")
    parser.add_argument("--rest-mark-archive", type=Path, default=_ROOT / "marks")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--max-polls", type=int)
    return parser


def config_from_args(args: argparse.Namespace) -> ObserverConfig:
    """Resolve explicit CLI values into isolated no-authority paths."""
    return ObserverConfig(
        paths=BrentoilOilShockShadowPaths(
            args.book_ledger,
            args.candle_ledger,
            args.cursor,
            args.journal,
            args.status,
            args.websocket_archive,
            args.rest_mark_archive,
        ),
        poll_seconds=float(args.poll_seconds),
        max_polls=args.max_polls,
    )


def run_observer(
    config: ObserverConfig,
    *,
    runner: _Runner,
    clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
    stop_requested: Callable[[], bool] = lambda: False,
) -> int:
    """Poll public evidence until bounded completion or a clean stop."""
    polls = 0
    while not stop_requested() and not _limit(config, polls):
        result = runner.poll(observed_at_ms=clock_ms())
        print(_poll_json(polls + 1, result), flush=True)
        polls += 1
        if not stop_requested() and not _limit(config, polls):
            sleeper(config.poll_seconds)
    return polls


def main(argv: Sequence[str] | None = None) -> int:
    """Run one singleton observer with signal-safe shutdown."""
    config = config_from_args(build_parser().parse_args(argv))
    stopping = threading.Event()

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        stopping.set()

    previous = {
        signal.SIGINT: signal.signal(signal.SIGINT, request_stop),
        signal.SIGTERM: signal.signal(signal.SIGTERM, request_stop),
    }
    try:
        runner = BrentoilOilShockShadowRunner(
            source=BrentoilOilShockPublicRestSource(), paths=config.paths
        )
        with cohort_checkpoint_runtime_lock(config.paths.status):
            run_observer(
                config,
                runner=runner,
                sleeper=stopping.wait,
                stop_requested=stopping.is_set,
            )
    finally:
        for current, handler in previous.items():
            signal.signal(current, handler)
    return 0


def _poll_json(poll: int, result: BrentoilOilShockShadowPollResult) -> str:
    payload = {
        "event_type": "brentoil_oil_shock_shadow_poll",
        "execution_authority": "none",
        "report_only": True,
        "poll": poll,
        "bootstrap": result.bootstrap,
        "decisions": len(result.decisions),
        "cursor_decision_time_ms": result.cursor_decision_time_ms,
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _limit(config: ObserverConfig, polls: int) -> bool:
    return config.max_polls is not None and polls >= config.max_polls


if __name__ == "__main__":
    raise SystemExit(main())
