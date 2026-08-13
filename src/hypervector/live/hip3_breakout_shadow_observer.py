"""Shared CLI loop for exact report-only HIP-3 breakout observers."""

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

from hypervector.live.mu_hip3_breakout_shadow import Hip3BreakoutShadowSpec
from hypervector.live.mu_hip3_breakout_shadow_runner import (
    MuHip3BreakoutShadowRunner,
    MuHip3PublicRestSource,
    MuHip3ShadowPollResult,
    MuHip3ShadowPaths,
)
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock


@dataclass(frozen=True)
class ObserverDefaults:
    """Default isolated paths for one exact report-only route."""

    asset: Path
    cohort: Path
    cursor: Path
    journal: Path
    status: Path


@dataclass(frozen=True)
class ObserverConfig:
    """Validated no-authority observer runtime boundaries."""

    paths: MuHip3ShadowPaths
    poll_seconds: float = 5.0
    max_polls: int | None = None
    execution_authority: str = "none"
    report_only: bool = True

    def __post_init__(self) -> None:
        """Reject invalid loops or any attempted authority escalation."""
        if self.poll_seconds <= 0.0:
            raise ValueError("HIP-3 shadow poll_seconds must be positive")
        if self.max_polls is not None and self.max_polls <= 0:
            raise ValueError("HIP-3 shadow max_polls must be positive")
        if self.execution_authority != "none" or self.report_only is not True:
            raise ValueError("HIP-3 shadow observer must remain report-only")


def build_parser(defaults: ObserverDefaults) -> argparse.ArgumentParser:
    """Build one standalone public-data observer command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-ledger", type=Path, default=defaults.asset)
    parser.add_argument("--cohort-ledger", type=Path, default=defaults.cohort)
    parser.add_argument("--cursor", type=Path, default=defaults.cursor)
    parser.add_argument("--journal", type=Path, default=defaults.journal)
    parser.add_argument("--status", type=Path, default=defaults.status)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--max-polls", type=int)
    return parser


def config_from_args(args: argparse.Namespace) -> ObserverConfig:
    """Resolve explicit CLI arguments into isolated research paths."""
    return ObserverConfig(
        paths=MuHip3ShadowPaths(
            args.asset_ledger,
            args.cohort_ledger,
            args.cursor,
            args.journal,
            args.status,
        ),
        poll_seconds=args.poll_seconds,
        max_polls=args.max_polls,
    )


def run_observer(
    config: ObserverConfig,
    *,
    runner: MuHip3BreakoutShadowRunner,
    event_type: str = "mu_hip3_breakout_shadow_poll",
    clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
    stop_requested: Callable[[], bool] = lambda: False,
) -> int:
    """Capture books and decisions without constructing an order client."""
    polls = 0
    while not stop_requested() and not _limit(config, polls):
        result = runner.poll(observed_at_ms=clock_ms())
        print(_poll_json(event_type, polls + 1, result), flush=True)
        polls += 1
        if not stop_requested() and not _limit(config, polls):
            sleeper(config.poll_seconds)
    return 0


def main_for(
    spec: Hip3BreakoutShadowSpec,
    defaults: ObserverDefaults,
    *,
    argv: Sequence[str] | None = None,
) -> int:
    """Run one exact singleton research writer with clean stop handling."""
    config = config_from_args(build_parser(defaults).parse_args(argv))
    stopping = threading.Event()

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        stopping.set()

    previous = {
        signal.SIGINT: signal.signal(signal.SIGINT, request_stop),
        signal.SIGTERM: signal.signal(signal.SIGTERM, request_stop),
    }
    try:
        runner = MuHip3BreakoutShadowRunner(
            source=MuHip3PublicRestSource(spec), paths=config.paths, spec=spec
        )
        with cohort_checkpoint_runtime_lock(config.paths.status):
            return run_observer(
                config,
                runner=runner,
                event_type=f"{_token(spec.symbol)}_hip3_breakout_shadow_poll",
                sleeper=stopping.wait,
                stop_requested=stopping.is_set,
            )
    finally:
        for current, handler in previous.items():
            signal.signal(current, handler)


def _poll_json(
    event_type: str,
    poll: int,
    result: MuHip3ShadowPollResult,
) -> str:
    payload = {
        "event_type": event_type,
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


def _token(symbol: str) -> str:
    if not symbol.startswith("xyz:"):
        raise ValueError("HIP-3 shadow symbol must use the xyz namespace")
    return symbol.removeprefix("xyz:").lower()
