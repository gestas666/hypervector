"""Publish a durable report-only checkpoint for the qualified HIP-3 roster."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
import json
import math
import os
from pathlib import Path
import signal
import threading
import time
from types import FrameType
from typing import Protocol

from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests import RequestException

from hypervector.live.hyperliquid_hip3_roster_factory import (
    create_read_only_hip3_roster_sources,
)
from hypervector.live.hyperliquid_sol_factory import SolSdkFactoryError
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.hip3_context_history import (
    append_context_record,
    prune_context_history,
    unavailable_context_record,
)
from hypervector.research.hip3_roster_observer import (
    ACTIVE_HIP3_MARKETS,
    Hip3RosterObserver,
    unavailable_hip3_roster_checkpoint,
)
from hypervector.runtime_env import load_wallet_env_if_present

_DEFAULT_OUTPUT = Path("data/runtime/research/hip3_roster_latest.json")
_DEFAULT_HISTORY = Path("data/research/hip3_asset_context")
# A full dex snapshot every poll is ~24 MB/day on the volume the live ledgers
# share; keep a working window rather than an unbounded archive.
_CONTEXT_RETENTION_DAYS = 30


class ObserverProtocol(Protocol):
    """Checkpoint collector surface accepted by the sidecar loop."""

    def snapshot(self, observed_at: datetime) -> dict[str, object]:
        """Return one complete available roster checkpoint."""
        ...


@dataclass(frozen=True)
class ObserverConfig:
    """Validated boundaries for the no-submit observer process."""

    output: Path = _DEFAULT_OUTPUT
    poll_seconds: float = 120.0
    max_polls: int | None = None
    context_history: Path | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.poll_seconds) or self.poll_seconds <= 0.0:
            raise ValueError("HIP-3 observer poll_seconds must be positive")
        if self.max_polls is not None and self.max_polls <= 0:
            raise ValueError("HIP-3 observer max_polls must be positive")


def build_parser() -> argparse.ArgumentParser:
    """Build the read-only HIP-3 observer command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--poll-seconds", type=float, default=120.0)
    parser.add_argument("--max-polls", type=int)
    parser.add_argument("--context-history", type=Path, default=_DEFAULT_HISTORY)
    return parser


def config_from_args(args: argparse.Namespace) -> ObserverConfig:
    """Resolve command-line values into validated observer boundaries."""
    return ObserverConfig(
        output=args.output,
        poll_seconds=args.poll_seconds,
        max_polls=args.max_polls,
        context_history=args.context_history,
    )


def run_observer(
    config: ObserverConfig,
    *,
    observer: ObserverProtocol,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleeper: Callable[[float], None] = time.sleep,
    stop_requested: Callable[[], bool] = lambda: False,
    archived_poll: Callable[[], bool] = lambda: False,
) -> int:
    """Poll venue truth and atomically publish available or unavailable state."""
    polls = 0
    successes = 0
    latest: dict[str, object] | None = None
    while not stop_requested() and not _reached_limit(config, polls):
        observed_at = clock()
        try:
            latest = observer.snapshot(observed_at)
            successes += 1
        except (
            OSError,
            ValueError,
            RequestException,
            ClientError,
            ServerError,
            SolSdkFactoryError,
            HyperliquidAdapterError,
        ) as exc:
            latest = unavailable_hip3_roster_checkpoint(
                observed_at=observed_at,
                error=exc,
            )
        polls += 1
        _publish(
            config,
            latest,
            lifecycle="running",
            polls=polls,
            archived=archived_poll(),
        )
        if not stop_requested() and not _reached_limit(config, polls):
            sleeper(config.poll_seconds)
    if latest is not None:
        _publish(config, latest, lifecycle="stopped", polls=polls)
    return 0 if successes > 0 or polls == 0 else 1


def _publish(
    config: ObserverConfig,
    payload: dict[str, object],
    *,
    lifecycle: str,
    polls: int,
    archived: bool = False,
) -> None:
    output = {**payload, "lifecycle": lifecycle, "polls": polls}
    write_atomic_json(config.output, output)
    if (
        config.context_history is not None
        and payload.get("status") == "unavailable"
        and lifecycle != "stopped"
        # The capture runs first: a poll it already archived is not a gap.
        and not archived
    ):
        error = payload.get("error")
        error_type = (
            str(error.get("type")) if isinstance(error, dict) else "UnknownError"
        )
        _archive_gap(config.context_history, error_type)
    event = {
        "event_type": "hip3_roster_observer_checkpoint",
        "status": output.get("status"),
        "lifecycle": lifecycle,
        "polls": polls,
        "execution_authority": "none",
        "recorded_at_utc": datetime.now(UTC).isoformat(),
    }
    print(json.dumps(event, separators=(",", ":"), sort_keys=True), flush=True)


def _archive_gap(directory: Path, error_type: str) -> None:
    """Record a missed poll without letting research storage stop the observer.

    This archive is report-only. Raising here converted one torn JSONL tail into an
    unrecoverable crash loop that left the roster telemetry the live supervisor
    reads permanently unavailable.
    """
    try:
        append_context_record(
            directory, unavailable_context_record(datetime.now(UTC), error_type)
        )
        prune_context_history(directory, retention_days=_CONTEXT_RETENTION_DAYS)
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "event_type": "hip3_context_history_unavailable",
                    "failure": type(exc).__name__,
                    "execution_authority": "none",
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            flush=True,
        )


def _reached_limit(config: ObserverConfig, polls: int) -> bool:
    return config.max_polls is not None and polls >= config.max_polls


def _build_observer(
    *, context_history: Path | None = None
) -> tuple[Hip3RosterObserver, Callable[[], bool]]:
    """Build the observer and a probe reporting whether this poll was archived."""
    symbols = tuple(spec.symbol for spec in ACTIVE_HIP3_MARKETS)
    sources = create_read_only_hip3_roster_sources(
        symbols=symbols,
        environ=os.environ,
    )
    funding = sources.funding
    source = funding.snapshot
    if context_history is not None:
        source = partial(funding.snapshot_with_capture, context_history)
    observer = Hip3RosterObserver(readers=sources.readers, funding_source=source)
    return observer, lambda: bool(getattr(funding, "last_capture_archived", False))


def _write_start_failure(config: ObserverConfig, error: Exception) -> int:
    payload = unavailable_hip3_roster_checkpoint(
        observed_at=datetime.now(UTC),
        error=error,
    )
    _publish(config, payload, lifecycle="failed_start", polls=0)
    return 1


def main() -> int:
    """Load only the public wallet identity and run the observer."""
    config = config_from_args(build_parser().parse_args())
    load_wallet_env_if_present()
    try:
        observer, archived_poll = _build_observer(
            context_history=config.context_history
        )
    except (OSError, ValueError, SolSdkFactoryError) as exc:
        return _write_start_failure(config, exc)
    stopping = threading.Event()

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        """Request a clean, interruptible observer stop."""
        stopping.set()

    def wait_for_stop(seconds: float) -> None:
        """Wait for the next poll or an operator stop signal."""
        stopping.wait(seconds)

    previous = {
        signal.SIGINT: signal.signal(signal.SIGINT, request_stop),
        signal.SIGTERM: signal.signal(signal.SIGTERM, request_stop),
    }
    try:
        return run_observer(
            config,
            observer=observer,
            sleeper=wait_for_stop,
            stop_requested=stopping.is_set,
            archived_poll=archived_poll,
        )
    finally:
        for current, handler in previous.items():
            signal.signal(current, handler)


if __name__ == "__main__":
    raise SystemExit(main())
