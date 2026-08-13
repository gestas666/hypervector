#!/usr/bin/env python3
"""Write one immutable report-only BTC 15-minute maker-entry artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from hypervector.research.market_cipher_maker_entry import MakerEntryConfig
from hypervector.research.market_cipher_maker_research import (
    run_market_cipher_maker_research,
)


def _parser() -> argparse.ArgumentParser:
    """Build the explicit paired-counterfactual command contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--funding", action="append", required=True, type=Path)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument(
        "--segment",
        required=True,
        choices=("development", "validation", "pseudo_holdout"),
    )
    parser.add_argument("--entry-ttl-seconds", type=int, default=300)
    parser.add_argument("--maximum-book-delay-ms", type=int, default=1_000)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run and persist one immutable paired maker-entry experiment."""
    args = _parser().parse_args(argv)
    output = Path(args.out)
    entries_path = output.with_suffix(".entries.parquet")
    trades_path = output.with_suffix(".trades.parquet")
    _ensure_available(output, entries_path, trades_path)
    run = run_market_cipher_maker_research(
        database_path=Path(args.database),
        baseline_path=Path(args.baseline),
        funding_paths=tuple(Path(path) for path in args.funding),
        start_utc=_timestamp(args.start),
        end_utc=_timestamp(args.end),
        segment=str(args.segment),
        entry_config=MakerEntryConfig(
            entry_ttl_seconds=int(args.entry_ttl_seconds),
            maximum_book_delay_ms=int(args.maximum_book_delay_ms),
        ),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    run.entries.to_parquet(entries_path, index=False)
    run.trades.to_parquet(trades_path, index=False)
    output.write_text(
        json.dumps(run.report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote report-only BTC maker-entry artifact: {output}")
    return 0


def _ensure_available(output: Path, *sidecars: Path) -> None:
    existing = [path for path in (output, *sidecars) if path.exists()]
    if existing:
        raise FileExistsError(
            "maker-entry output exists: " + ", ".join(str(path) for path in existing)
        )


def _timestamp(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError("maker-entry timestamps must include a timezone")
    return timestamp.tz_convert("UTC")


if __name__ == "__main__":
    raise SystemExit(main())
