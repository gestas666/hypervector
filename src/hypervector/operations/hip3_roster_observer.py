"""Publish a durable report-only checkpoint for a configured HIP-3 market roster.

The markets come from a cohort profile's HIP-3 assets (``--config``, each with
its ``venue_max_leverage``) or from explicit ``--market dex:ASSET=MAX_LEVERAGE``
values. Only the public wallet address is loaded.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
import json
import math
import os
from pathlib import Path
import signal
import sys
import threading
import time
from types import FrameType
from typing import Protocol

from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests import RequestException

from hypervector.live.hyperliquid_hip3_roster_factory import (
    create_read_only_hip3_roster_sources,
)
from hypervector.live.hyperliquid_sdk_factory import HyperliquidSdkFactoryError
from hypervector.live.hyperliquid_parsing import HyperliquidAdapterError
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.perp_venue_identity import parse_perp_venue_identity
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.hip3_context_history import (
    append_context_record,
    prune_context_history,
    unavailable_context_record,
)
from hypervector.research.hip3_roster_observer import (
    Hip3MarketSpec,
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

    markets: tuple[Hip3MarketSpec, ...]
    output: Path = _DEFAULT_OUTPUT
    poll_seconds: float = 120.0
    max_polls: int | None = None
    context_history: Path | None = None

    def __post_init__(self) -> None:
        if not self.markets:
            raise ValueError("HIP-3 observer requires at least one market")
        symbols = [spec.symbol for spec in self.markets]
        if len(set(symbols)) != len(symbols):
            raise ValueError("HIP-3 observer markets must be unique")
        if not math.isfinite(self.poll_seconds) or self.poll_seconds <= 0.0:
            raise ValueError("HIP-3 observer poll_seconds must be positive")
        if self.max_polls is not None and self.max_polls <= 0:
            raise ValueError("HIP-3 observer max_polls must be positive")

    @property
    def symbols(self) -> tuple[str, ...]:
        """Return the configured roster in order."""
        return tuple(spec.symbol for spec in self.markets)


def build_parser() -> argparse.ArgumentParser:
    """Build the read-only HIP-3 observer command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        help="cohort profile whose HIP-3 assets form the roster",
    )
    parser.add_argument(
        "--market",
        action="append",
        default=[],
        help="explicit roster market as dex:ASSET=MAX_LEVERAGE; repeatable",
    )
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--poll-seconds", type=float, default=120.0)
    parser.add_argument("--max-polls", type=int)
    parser.add_argument("--context-history", type=Path, default=_DEFAULT_HISTORY)
    return parser


def config_from_args(args: argparse.Namespace) -> ObserverConfig:
    """Resolve command-line values into validated observer boundaries."""
    return ObserverConfig(
        markets=roster_markets(args.config, tuple(args.market)),
        output=args.output,
        poll_seconds=args.poll_seconds,
        max_polls=args.max_polls,
        context_history=args.context_history,
    )


def roster_markets(
    config_path: Path | None, explicit: tuple[str, ...]
) -> tuple[Hip3MarketSpec, ...]:
    """Return the roster from exactly one of a cohort profile or explicit markets."""
    if (config_path is None) == (not explicit):
        raise ValueError("HIP-3 roster requires exactly one of --config or --market")
    if config_path is not None:
        config = load_multi_asset_live_config(config_path, mode="observe")
        markets = tuple(
            Hip3MarketSpec(asset.symbol, int(asset.venue_max_leverage))
            for asset in config.assets
            if parse_perp_venue_identity(asset.symbol).perp_dex
        )
        if not markets:
            raise ValueError(f"cohort profile has no HIP-3 assets: {config_path}")
        return markets
    return tuple(_explicit_market(value) for value in explicit)


def _explicit_market(value: str) -> Hip3MarketSpec:
    symbol, separator, leverage = value.partition("=")
    if not separator or not leverage.strip().isdigit():
        raise ValueError(f"--market must be dex:ASSET=MAX_LEVERAGE: {value!r}")
    identity = parse_perp_venue_identity(symbol.strip())
    if not identity.perp_dex:
        raise ValueError(f"--market must name a HIP-3 market: {value!r}")
    return Hip3MarketSpec(identity.symbol, int(leverage))


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
            HyperliquidSdkFactoryError,
            HyperliquidAdapterError,
        ) as exc:
            latest = unavailable_hip3_roster_checkpoint(
                observed_at=observed_at,
                error=exc,
                symbols=config.symbols,
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
    markets: tuple[Hip3MarketSpec, ...],
    *,
    context_history: Path | None = None,
) -> tuple[Hip3RosterObserver, Callable[[], bool]]:
    """Build the observer and a probe reporting whether this poll was archived."""
    sources = create_read_only_hip3_roster_sources(
        symbols=tuple(spec.symbol for spec in markets),
        environ=os.environ,
    )
    funding = sources.funding
    source = funding.snapshot
    if context_history is not None:
        source = partial(funding.snapshot_with_capture, context_history)
    observer = Hip3RosterObserver(
        readers=sources.readers, markets=markets, funding_source=source
    )
    return observer, lambda: bool(getattr(funding, "last_capture_archived", False))


def _write_start_failure(config: ObserverConfig, error: Exception) -> int:
    payload = unavailable_hip3_roster_checkpoint(
        observed_at=datetime.now(UTC),
        error=error,
        symbols=config.symbols,
    )
    _publish(config, payload, lifecycle="failed_start", polls=0)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Load only the public wallet identity and run the observer."""
    try:
        config = config_from_args(build_parser().parse_args(argv))
    except (OSError, ValueError) as exc:
        print(f"HIP-3 roster observer refused: {exc}", file=sys.stderr)
        return 2
    load_wallet_env_if_present()
    try:
        observer, archived_poll = _build_observer(
            config.markets, context_history=config.context_history
        )
    except (OSError, ValueError, HyperliquidSdkFactoryError) as exc:
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
