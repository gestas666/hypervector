"""Record public Hyperliquid market evidence without execution authority."""

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

from hypervector.data.hl_event_stream import RecordedEvent
from hypervector.data.hl_events import (
    AssetContextEvent,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
)
from hypervector.data.oxa_api import validate_market_symbol
from hypervector.paper.event_stream_pump import HypervelocityEventStreamPump

_DEFAULT_BATCH_SIZE = 2_000
_DEFAULT_POLL_SECONDS = 0.25
_DEFAULT_STATUS_SECONDS = 30.0
_DEFAULT_FLUSH_SECONDS = 30.0


class RecorderPump(Protocol):
    """Public-data pump required by the archive-only runner."""

    def start(self) -> None:
        """Start receiving public market events."""

    def pump(self, consumer: ArchiveOnlyConsumer) -> int:
        """Archive and deliver the current event batch."""

    def flush(self) -> None:
        """Persist the accepted event tail without stopping capture."""

    def close(self) -> None:
        """Stop the feed and flush its archive."""


@dataclass(frozen=True)
class RecorderConfig:
    """Validated boundaries for one archive-only recorder process."""

    symbol: str
    data_root: Path
    archive_batch_size: int = _DEFAULT_BATCH_SIZE
    poll_seconds: float = _DEFAULT_POLL_SECONDS
    status_seconds: float = _DEFAULT_STATUS_SECONDS
    flush_seconds: float = _DEFAULT_FLUSH_SECONDS
    max_polls: int | None = None

    def __post_init__(self) -> None:
        family = "hip3" if ":" in self.symbol else "core"
        validate_market_symbol(self.symbol, family)
        if self.archive_batch_size <= 0:
            raise ValueError("archive_batch_size must be positive")
        if self.poll_seconds <= 0.0:
            raise ValueError("poll_seconds must be positive")
        if self.status_seconds <= 0.0:
            raise ValueError("status_seconds must be positive")
        if self.flush_seconds <= 0.0:
            raise ValueError("flush_seconds must be positive")
        if self.max_polls is not None and self.max_polls <= 0:
            raise ValueError("max_polls must be positive when configured")

    @property
    def archive_path(self) -> Path:
        """Return the immutable event-dataset root for this symbol."""
        return self.data_root / "cache" / "events" / "hyperliquid" / self.symbol


@dataclass
class ArchiveOnlyConsumer:
    """Count archived market evidence and expose no order-submission surface."""

    symbol: str
    l2_snapshots: int = 0
    public_trades: int = 0
    asset_contexts: int = 0
    stream_gaps: int = 0

    def ingest_hyperliquid_event(self, event: RecordedEvent) -> str | None:
        """Validate and count one event already written by the pump."""
        if event.symbol != self.symbol:
            raise ValueError(f"event symbol {event.symbol!r} != {self.symbol!r}")
        if isinstance(event, L2SnapshotEvent):
            self.l2_snapshots += 1
        elif isinstance(event, PublicTradeEvent):
            self.public_trades += 1
        elif isinstance(event, AssetContextEvent):
            self.asset_contexts += 1
        elif isinstance(event, StreamGap):
            self.stream_gaps += 1
        else:
            raise TypeError(f"unsupported recorder event {type(event).__name__}")
        return None

    def snapshot(self) -> dict[str, int]:
        """Return monotonically increasing evidence counts."""
        total = (
            self.l2_snapshots
            + self.public_trades
            + self.asset_contexts
            + self.stream_gaps
        )
        return {
            "l2_snapshots": self.l2_snapshots,
            "public_trades": self.public_trades,
            "asset_contexts": self.asset_contexts,
            "stream_gaps": self.stream_gaps,
            "total_events": total,
        }


def build_parser() -> argparse.ArgumentParser:
    """Build the archive-only mainnet recorder command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTC")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--archive-batch-size", type=int, default=_DEFAULT_BATCH_SIZE)
    parser.add_argument("--poll-seconds", type=float, default=_DEFAULT_POLL_SECONDS)
    parser.add_argument("--status-seconds", type=float, default=_DEFAULT_STATUS_SECONDS)
    parser.add_argument("--flush-seconds", type=float, default=_DEFAULT_FLUSH_SECONDS)
    parser.add_argument("--max-polls", type=int)
    return parser


def config_from_args(args: argparse.Namespace) -> RecorderConfig:
    """Resolve CLI values into a validated recorder configuration."""
    return RecorderConfig(
        symbol=_normalize_cli_symbol(str(args.symbol)),
        data_root=Path(args.data_root),
        archive_batch_size=int(args.archive_batch_size),
        poll_seconds=float(args.poll_seconds),
        status_seconds=float(args.status_seconds),
        flush_seconds=float(args.flush_seconds),
        max_polls=args.max_polls,
    )


def _normalize_cli_symbol(value: str) -> str:
    """Normalize user case while retaining canonical HIP-3 dex identity."""
    symbol = value.strip()
    if ":" not in symbol:
        return symbol.upper()
    dex, separator, asset = symbol.partition(":")
    if not separator:
        raise ValueError("HIP-3 symbol must contain a dex and asset")
    normalized = f"{dex.lower()}:{asset.upper()}"
    validate_market_symbol(normalized, "hip3")
    return normalized


def run_recorder(
    config: RecorderConfig,
    *,
    pump: RecorderPump | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    stop_requested: Callable[[], bool] = lambda: False,
) -> int:
    """Run a public-data recorder and flush its archive on every clean exit."""
    active_pump = pump or HypervelocityEventStreamPump(
        data_root=config.data_root,
        symbol=config.symbol,
        archive_batch_size=config.archive_batch_size,
    )
    consumer = ArchiveOnlyConsumer(config.symbol)
    polls = 0
    reason = "bounded_completion"
    _print_status("market_event_recorder_started", config, consumer)
    active_pump.start()
    next_status = monotonic() + config.status_seconds
    next_flush = monotonic() + config.flush_seconds
    try:
        while not stop_requested():
            active_pump.pump(consumer)
            polls += 1
            now = monotonic()
            if now >= next_flush:
                active_pump.flush()
                next_flush = now + config.flush_seconds
            if now >= next_status:
                _print_status("market_event_recorder_heartbeat", config, consumer)
                next_status = now + config.status_seconds
            if config.max_polls is not None and polls >= config.max_polls:
                break
            sleeper(config.poll_seconds)
        if stop_requested():
            reason = "stop_requested"
    except KeyboardInterrupt:
        reason = "keyboard_interrupt"
    finally:
        active_pump.close()
        _print_status("market_event_recorder_stopped", config, consumer, reason)
    return 0


def main() -> int:
    """Run until SIGINT/SIGTERM while preserving a final archive flush."""
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


def _print_status(
    event_type: str,
    config: RecorderConfig,
    consumer: ArchiveOnlyConsumer,
    reason: str | None = None,
) -> None:
    row: dict[str, object] = {
        "event_type": event_type,
        "symbol": config.symbol,
        "execution_authority": "none",
        "channels": ["l2Book", "trades", "activeAssetCtx"],
        "archive_path": str(config.archive_path),
        "counts": consumer.snapshot(),
        "recorded_at_ns": time.time_ns(),
    }
    if reason is not None:
        row["reason"] = reason
    print(json.dumps(row, separators=(",", ":"), sort_keys=True), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
