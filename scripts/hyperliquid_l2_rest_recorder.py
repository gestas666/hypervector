"""Record isolated one-second public Hyperliquid L2 research evidence."""

from __future__ import annotations

import argparse
import json
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Protocol

from requests.exceptions import RequestException

from hypervector.data.event_archive import EventArchive
from hypervector.data.hl_events import L2SnapshotEvent
from hypervector.data.hl_rest_l2_recorder import HyperliquidRestL2Recorder

_MINIMUM_POLL_SECONDS = 0.5
_DEFAULT_POLL_SECONDS = 1.0
_DEFAULT_BATCH_SIZE = 2_000
_DEFAULT_STATUS_SECONDS = 30.0
_RATE_LIMIT_BACKOFF_SECONDS = 5.0
_L2_REQUEST_WEIGHT = 2.0
_ARCHIVE_NAMESPACE = "hyperliquid_rest_1s"


class RestRecorderProtocol(Protocol):
    """Public-data recorder boundary with no order-submission surface."""

    def poll(self) -> L2SnapshotEvent:
        """Fetch and archive one public L2 snapshot."""

    def declare_gap(self, *, detected_ts_ns: int, reason: str) -> None:
        """Retain one failed polling interval explicitly."""

    def close(self) -> None:
        """Flush the archive and retain any unresolved gap."""

    def flush(self) -> None:
        """Persist the current archive tail without stopping capture."""


@dataclass(frozen=True)
class RecorderConfig:
    """Validated boundaries for one research-only recorder process."""

    symbol: str
    data_root: Path
    poll_seconds: float = _DEFAULT_POLL_SECONDS
    archive_batch_size: int = _DEFAULT_BATCH_SIZE
    status_seconds: float = _DEFAULT_STATUS_SECONDS
    flush_seconds: float = _DEFAULT_STATUS_SECONDS
    max_polls: int | None = None

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("symbol must be a non-empty uppercase venue symbol")
        if self.poll_seconds < _MINIMUM_POLL_SECONDS:
            raise ValueError("poll_seconds must be at least 0.5")
        if self.archive_batch_size <= 0:
            raise ValueError("archive_batch_size must be positive")
        if self.status_seconds <= 0.0:
            raise ValueError("status_seconds must be positive")
        if self.flush_seconds <= 0.0:
            raise ValueError("flush_seconds must be positive")
        if self.max_polls is not None and self.max_polls <= 0:
            raise ValueError("max_polls must be positive when configured")

    @property
    def archive_path(self) -> Path:
        """Return the transport-isolated event-dataset root."""
        return self.data_root / "cache" / "events" / _ARCHIVE_NAMESPACE / self.symbol

    @property
    def estimated_request_weight_per_minute(self) -> float:
        """Return the configured public REST request-weight estimate."""
        return _L2_REQUEST_WEIGHT * 60.0 / self.poll_seconds


@dataclass
class RecorderCounts:
    """Monotonic runtime counters for structured telemetry."""

    attempts: int = 0
    errors: int = 0
    snapshots: int = 0

    def as_dict(self) -> dict[str, int]:
        """Return JSON-ready recorder counts."""
        return {
            "attempts": self.attempts,
            "errors": self.errors,
            "snapshots": self.snapshots,
        }


def build_parser() -> argparse.ArgumentParser:
    """Build the public, mainnet, execution-incapable recorder command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="HYPE")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--poll-seconds", type=float, default=_DEFAULT_POLL_SECONDS)
    parser.add_argument("--archive-batch-size", type=int, default=_DEFAULT_BATCH_SIZE)
    parser.add_argument("--status-seconds", type=float, default=_DEFAULT_STATUS_SECONDS)
    parser.add_argument("--flush-seconds", type=float, default=_DEFAULT_STATUS_SECONDS)
    parser.add_argument("--max-polls", type=int)
    return parser


def config_from_args(args: argparse.Namespace) -> RecorderConfig:
    """Resolve command-line values into validated recorder boundaries."""
    return RecorderConfig(
        symbol=str(args.symbol).strip().upper(),
        data_root=Path(args.data_root),
        poll_seconds=float(args.poll_seconds),
        archive_batch_size=int(args.archive_batch_size),
        status_seconds=float(args.status_seconds),
        flush_seconds=float(args.flush_seconds),
        max_polls=args.max_polls,
    )


def run_recorder(
    config: RecorderConfig,
    *,
    recorder: RestRecorderProtocol | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    clock_ns: Callable[[], int] = time.time_ns,
    stop_requested: Callable[[], bool] = lambda: False,
) -> int:
    """Poll public L2 at bounded cadence and close durably on every exit."""
    active = recorder or _build_recorder(config)
    counts = RecorderCounts()
    next_poll = monotonic()
    next_status = next_poll + config.status_seconds
    next_flush = next_poll + config.flush_seconds
    reason = "bounded_completion"
    _print_status("rest_l2_recorder_started", config, counts)
    try:
        while not stop_requested() and not _reached_limit(config, counts):
            next_poll = _wait_until(next_poll, monotonic, sleeper)
            backoff = _poll_once(active, counts, clock_ns, config)
            now = monotonic()
            next_poll = max(next_poll + config.poll_seconds, now + backoff)
            if now >= next_flush:
                active.flush()
                next_flush = now + config.flush_seconds
            if now >= next_status:
                _print_status("rest_l2_recorder_heartbeat", config, counts)
                next_status = now + config.status_seconds
        if stop_requested():
            reason = "stop_requested"
    except KeyboardInterrupt:
        reason = "keyboard_interrupt"
    finally:
        active.close()
        _print_status("rest_l2_recorder_stopped", config, counts, reason=reason)
    return 0


def _poll_once(
    recorder: RestRecorderProtocol,
    counts: RecorderCounts,
    clock_ns: Callable[[], int],
    config: RecorderConfig,
) -> float:
    counts.attempts += 1
    try:
        recorder.poll()
    except RequestException as exc:
        counts.errors += 1
        reason = _request_error_reason(exc)
        recorder.declare_gap(detected_ts_ns=clock_ns(), reason=reason)
        _print_status("rest_l2_recorder_degraded", config, counts, reason=reason)
        return _RATE_LIMIT_BACKOFF_SECONDS if reason == "http_429" else 0.0
    counts.snapshots += 1
    return 0.0


def _request_error_reason(error: RequestException) -> str:
    response = error.response
    if response is not None and response.status_code is not None:
        return f"http_{response.status_code}"
    return type(error).__name__.lower()


def _wait_until(
    deadline: float,
    monotonic: Callable[[], float],
    sleeper: Callable[[float], None],
) -> float:
    now = monotonic()
    if deadline > now:
        sleeper(deadline - now)
    return deadline


def _reached_limit(config: RecorderConfig, counts: RecorderCounts) -> bool:
    return config.max_polls is not None and counts.attempts >= config.max_polls


def _build_recorder(config: RecorderConfig) -> HyperliquidRestL2Recorder:
    from hyperliquid.info import Info  # type: ignore[import-untyped]
    from hyperliquid.utils.constants import MAINNET_API_URL  # type: ignore[import-untyped]

    archive = EventArchive(
        data_root=config.data_root,
        symbol=config.symbol,
        batch_size=config.archive_batch_size,
        namespace=_ARCHIVE_NAMESPACE,
    )
    return HyperliquidRestL2Recorder(
        info=Info(MAINNET_API_URL, skip_ws=True),
        archive=archive,
        symbol=config.symbol,
    )


def _print_status(
    event_type: str,
    config: RecorderConfig,
    counts: RecorderCounts,
    *,
    reason: str | None = None,
) -> None:
    row: dict[str, object] = {
        "event_type": event_type,
        "symbol": config.symbol,
        "execution_authority": "none",
        "transport": "public_rest_l2_snapshot",
        "poll_seconds": config.poll_seconds,
        "estimated_request_weight_per_minute": (
            config.estimated_request_weight_per_minute
        ),
        "archive_path": str(config.archive_path),
        "counts": counts.as_dict(),
        "recorded_at_ns": time.time_ns(),
    }
    if reason is not None:
        row["reason"] = reason
    print(json.dumps(row, separators=(",", ":"), sort_keys=True), flush=True)


def main() -> int:
    """Install clean stop handlers and run the public-data recorder."""
    config = config_from_args(build_parser().parse_args())
    stopping = threading.Event()

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        stopping.set()

    previous = {
        signal.SIGINT: signal.signal(signal.SIGINT, request_stop),
        signal.SIGTERM: signal.signal(signal.SIGTERM, request_stop),
    }
    try:
        return run_recorder(config, stop_requested=stopping.is_set)
    finally:
        for current, handler in previous.items():
            signal.signal(current, handler)


if __name__ == "__main__":
    raise SystemExit(main())
