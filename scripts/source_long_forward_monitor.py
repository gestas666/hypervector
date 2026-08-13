"""Resolve source-faithful BTC long observations from recorded public events."""

from __future__ import annotations

import argparse
import json
import signal
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType

from hypervector.data.event_archive import EventArchive
from hypervector.research.source_follow_portfolio_models import (
    SourcePortfolioReplayConfig,
)
from hypervector.research.source_long_forward_monitor import (
    SourceLongForwardMonitor,
    SourceLongOutcomeLedger,
)
from hypervector.strategies.source_follow_profile import (
    SourceFollowHypervelocityProfile,
    load_source_follow_profile,
)

_DEFAULT_BACKEND_LEDGER = Path("data/live/hypervelocity_source_follow/decisions.jsonl")
_DEFAULT_OUTCOME_LEDGER = Path(
    "data/live/hypervelocity_source_follow/source_long_outcomes.jsonl"
)
_DEFAULT_PROFILE = Path(
    "configs/hypervelocity_source_follow_bidirectional_minrange12_alloc35_shadow.toml"
)
_DEFAULT_POLL_SECONDS = 30.0


def build_parser() -> argparse.ArgumentParser:
    """Build the observe-only forward outcome command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--profile", type=Path, default=_DEFAULT_PROFILE)
    parser.add_argument("--backend-ledger", type=Path, default=_DEFAULT_BACKEND_LEDGER)
    parser.add_argument("--outcome-ledger", type=Path, default=_DEFAULT_OUTCOME_LEDGER)
    parser.add_argument("--poll-seconds", type=float, default=_DEFAULT_POLL_SECONDS)
    parser.add_argument("--max-polls", type=int)
    parser.add_argument("--once", action="store_true")
    return parser


def build_base_config(
    profile: SourceFollowHypervelocityProfile,
) -> SourcePortfolioReplayConfig:
    """Project the authoritative source profile into the production matcher."""
    return SourcePortfolioReplayConfig(
        initial_equity=profile.initial_cash_usd,
        margin_fraction=profile.margin_fraction,
        leverage=profile.leverage,
        target_price_fraction=(profile.target_margin_pct / profile.leverage / 100.0),
        entry_pulse_seconds=profile.entry_pulse_seconds,
        entry_ttl_seconds=profile.entry_ttl_seconds,
        maximum_hold_seconds=profile.maximum_hold_seconds,
        maker_fee_rate=profile.maker_fee_rate,
        taker_fee_rate=profile.taker_fee_rate,
        submit_latency_ms=profile.execution_submit_latency_ms,
        cancel_latency_ms=profile.execution_cancel_latency_ms,
        max_event_age_ms=profile.execution_max_event_age_ms,
        size_decimals=profile.size_decimals,
        price_tick=1.0,
        receipt_timestamp_source="recorded",
    )


def run_monitor(args: argparse.Namespace, stopping: threading.Event) -> int:
    """Poll append-only decisions and resolve them from immutable event tape."""
    _validate_args(args)
    profile = load_source_follow_profile(args.profile)
    archive = EventArchive(data_root=args.data_root, symbol="BTC", batch_size=1)
    monitor = SourceLongForwardMonitor(
        backend_ledger=args.backend_ledger,
        archive=archive,
        outcome_ledger=SourceLongOutcomeLedger(args.outcome_ledger),
        base_config=build_base_config(profile),
    )
    _print_identity(args, profile)
    polls = 0
    while not stopping.is_set():
        rows = monitor.poll(datetime.now(UTC))
        for row in rows:
            print(json.dumps(row, separators=(",", ":"), sort_keys=True), flush=True)
        polls += 1
        if args.once or (args.max_polls is not None and polls >= args.max_polls):
            break
        stopping.wait(args.poll_seconds)
    return 0


def main() -> int:
    """Install flush-safe stop handlers and run the no-submit monitor."""
    args = build_parser().parse_args()
    stopping = threading.Event()

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        stopping.set()

    previous = {
        signal.SIGINT: signal.signal(signal.SIGINT, request_stop),
        signal.SIGTERM: signal.signal(signal.SIGTERM, request_stop),
    }
    try:
        return run_monitor(args, stopping)
    finally:
        for current, handler in previous.items():
            signal.signal(current, handler)


def _validate_args(args: argparse.Namespace) -> None:
    if args.poll_seconds <= 0.0:
        raise ValueError("poll_seconds must be positive")
    if args.max_polls is not None and args.max_polls <= 0:
        raise ValueError("max_polls must be positive when configured")


def _print_identity(
    args: argparse.Namespace,
    profile: SourceFollowHypervelocityProfile,
) -> None:
    row = {
        "event_type": "source_long_forward_monitor_started",
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "execution_authority": "none",
        "symbol": "BTC",
        "backend_ledger": str(args.backend_ledger),
        "outcome_ledger": str(args.outcome_ledger),
        "event_archive": str(
            args.data_root / "cache" / "events" / "hyperliquid" / "BTC"
        ),
        "execution_model": "production_maker_trade_through_counterfactual",
        "portfolio_interaction": "independent_observer_not_shared_execution",
        "profile_id": profile.profile_id,
        "fees": {
            "maker_rate": profile.maker_fee_rate,
            "taker_rate": profile.taker_fee_rate,
        },
    }
    print(json.dumps(row, separators=(",", ":"), sort_keys=True), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
