"""Define the exact report-only SP500/SPCX observer process pair."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import signal
import sys
import threading
from types import FrameType

from hypervector.live.hip3_index_observer_supervisor import (
    IndexObserverRoute,
    IndexObserverSupervisorConfig,
    supervise_index_observers,
)
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock


_OBSERVER = "scripts/index_hip3_breakout_shadow_observe.py"
_RESEARCH = Path("data/live/research")
_RUNTIME = Path("data/runtime/research")
_STATUS = _RUNTIME / "hip3_index_observer_supervisor_latest.json"


def default_routes() -> tuple[IndexObserverRoute, ...]:
    """Return the exact unsigned index observer commands and durable files."""
    return tuple(_route(symbol) for symbol in ("xyz:SP500", "xyz:SPCX"))


def build_parser() -> argparse.ArgumentParser:
    """Build the order-incapable process supervisor CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=Path, default=_STATUS)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--warmup-seconds", type=float, default=45.0)
    parser.add_argument("--stop-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--maximum-restarts-per-route", type=int, default=3)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Hold singleton ownership while supervising both unsigned observers."""
    args = build_parser().parse_args(argv)
    config = IndexObserverSupervisorConfig(
        status=args.status,
        poll_seconds=args.poll_seconds,
        warmup_seconds=args.warmup_seconds,
        stop_timeout_seconds=args.stop_timeout_seconds,
        maximum_restarts_per_route=args.maximum_restarts_per_route,
    )
    stopping = threading.Event()

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        stopping.set()

    previous = {
        signal.SIGINT: signal.signal(signal.SIGINT, request_stop),
        signal.SIGTERM: signal.signal(signal.SIGTERM, request_stop),
    }
    try:
        with cohort_checkpoint_runtime_lock(config.status):
            return supervise_index_observers(
                config,
                default_routes(),
                stop_requested=stopping.is_set,
            )
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _route(symbol: str) -> IndexObserverRoute:
    token = symbol.removeprefix("xyz:").lower()
    return IndexObserverRoute(
        symbol=symbol,
        command=(sys.executable, _OBSERVER, "--symbol", symbol),
        status=_RUNTIME / f"xyz_{token}_fresh15_v3_latest.json",
        cursor=_RUNTIME / f"xyz_{token}_fresh15_v3_cursor.json",
        journal=_RESEARCH / f"xyz_{token}_fresh15_v3_decisions.jsonl",
        log=_RUNTIME / f"xyz_{token}_fresh15_v3_supervised.log",
    )


if __name__ == "__main__":
    raise SystemExit(main())
