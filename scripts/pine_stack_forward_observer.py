#!/usr/bin/env python3
"""Run the zero-capital ETH 30m four-Pine forward observer."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import time

import pandas as pd

from hypervector.data.hl import fetch_hl_ohlcv
from hypervector.research.pine_stack_forward_observer import (
    PineStackForwardObserver,
    prepare_completed_pine_features,
)

_DEFAULT_LEDGER = Path("data/research/forward/pine_stack_eth30/decisions.jsonl")
_DEFAULT_STOP = Path("data/research/forward/pine_stack_eth30/STOP")


def build_parser() -> argparse.ArgumentParser:
    """Return the no-submit observer command contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", choices=("ETH",), default="ETH")
    parser.add_argument("--bar-minutes", choices=(30,), type=int, default=30)
    parser.add_argument("--ledger", type=Path, default=_DEFAULT_LEDGER)
    parser.add_argument("--stop-file", type=Path, default=_DEFAULT_STOP)
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--max-polls", type=int)
    parser.add_argument("--once", action="store_true")
    return parser


def run_observer(args: argparse.Namespace) -> int:
    """Poll public candles and append completed backend feature rows."""
    _validate_args(args)
    args.stop_file.unlink(missing_ok=True)
    activated = pd.Timestamp(datetime.now(UTC))
    observer = PineStackForwardObserver(
        activated_at=activated,
        ledger_path=args.ledger,
        symbol=args.symbol,
    )
    bars = fetch_hl_ohlcv(args.symbol, "1m", args.lookback_days)
    polls = 0
    while not args.stop_file.exists():
        observed = pd.Timestamp(datetime.now(UTC))
        features = prepare_completed_pine_features(
            bars,
            observed_at=observed,
            bar_minutes=args.bar_minutes,
        )
        rows = observer.observe(features, observed_at=observed)
        print(
            f"{observed.isoformat()} pine_stack_rows={len(rows)} "
            f"last_bar={features['decision_time_utc'].iloc[-1].isoformat()}"
        )
        polls += 1
        if args.once or (args.max_polls is not None and polls >= args.max_polls):
            break
        time.sleep(args.poll_seconds)
        tail = fetch_hl_ohlcv(args.symbol, "1m", 1)
        bars = _merge_bars(bars, tail, observed, args.lookback_days)
    return 0


def _merge_bars(
    existing: pd.DataFrame,
    tail: pd.DataFrame,
    observed_at: pd.Timestamp,
    lookback_days: int,
) -> pd.DataFrame:
    combined = pd.concat([existing, tail], ignore_index=True)
    combined = combined.sort_values("timestamp").drop_duplicates(
        subset=["timestamp"], keep="last"
    )
    cutoff = observed_at - pd.Timedelta(days=lookback_days)
    return combined.loc[combined["timestamp"].ge(cutoff)].reset_index(drop=True)


def _validate_args(args: argparse.Namespace) -> None:
    if args.lookback_days < 2:
        raise ValueError("Pine observer lookback-days must be at least two")
    if args.poll_seconds <= 0.0:
        raise ValueError("Pine observer poll-seconds must be positive")
    if args.max_polls is not None and args.max_polls < 1:
        raise ValueError("Pine observer max-polls must be positive")


def main() -> int:
    """Load arguments and run the zero-capital observer."""
    return run_observer(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
