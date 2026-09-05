#!/usr/bin/env python3
"""Publish immutable report-only market-diversification evidence for v51."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd

from hypervector.data.hl import fetch_hl_ohlcv_snapshot
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.mu_hip3_artifacts import require_new_outputs
from hypervector.research.v51_candidate_market_diversification import (
    CandidateMarketDiversificationConfig,
    build_candidate_market_diversification_report,
)

_BASELINE_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE", "xyz:SP500", "xyz:SPCX")
_CANDIDATE_SYMBOLS = ("xyz:BRENTOIL", "xyz:MU")
_REPO_ROOT = Path(__file__).resolve().parents[1]
_GENERATOR_FILES = (
    "pyproject.toml",
    "uv.lock",
    "scripts/v51_candidate_market_diversification.py",
    "src/hypervector/data/hl.py",
    "src/hypervector/data/oxa_storage.py",
    "src/hypervector/research/v51_candidate_market_diversification.py",
)


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable report command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=_utc_timestamp)
    parser.add_argument("--end", required=True, type=_utc_timestamp)
    parser.add_argument("--baseline-symbol", action="append", dest="baseline_symbols")
    parser.add_argument("--candidate-symbol", action="append", dest="candidate_symbols")
    parser.add_argument("--minimum-shared-returns", type=int, default=720)
    parser.add_argument("--chronological-folds", type=int, default=3)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def run_command(args: argparse.Namespace) -> dict[str, object]:
    """Fetch one common public window and publish immutable evidence."""
    require_new_outputs(args.output)
    generator = _generator_identity()
    start = args.start
    end = args.end
    if start >= end:
        raise ValueError("market-diversification window must be positive")
    baseline_symbols = tuple(args.baseline_symbols or _BASELINE_SYMBOLS)
    candidate_symbols = tuple(args.candidate_symbols or _CANDIDATE_SYMBOLS)
    symbols = baseline_symbols + candidate_symbols
    lookback_days = float((end - start) / pd.Timedelta(days=1))
    end_ms = int(end.timestamp() * 1000)
    frames = {
        symbol: fetch_hl_ohlcv_snapshot(symbol, "1h", lookback_days, end_ms=end_ms)
        for symbol in symbols
    }
    config = CandidateMarketDiversificationConfig(
        baseline_symbols=baseline_symbols,
        candidate_symbols=candidate_symbols,
        start_utc=start,
        end_utc=end,
        minimum_shared_returns=args.minimum_shared_returns,
        chronological_folds=args.chronological_folds,
    )
    report = build_candidate_market_diversification_report(frames, config)
    report["generated_at_utc"] = datetime.now(UTC).isoformat()
    report["provenance"] = {"generator_files": generator}
    if _generator_identity() != generator:
        raise RuntimeError(
            "market-diversification generator changed during acquisition"
        )
    write_immutable_json(args.output, report)
    return report


def _generator_identity() -> dict[str, dict[str, object]]:
    return {
        relative: file_evidence(_REPO_ROOT / relative) for relative in _GENERATOR_FILES
    }


def _utc_timestamp(value: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"invalid UTC timestamp: {value}") from exc
    if timestamp.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return timestamp.tz_convert("UTC")


def main(argv: list[str] | None = None) -> int:
    """Run the report-only eight-asset market-diversification command."""
    report = run_command(build_parser().parse_args(argv))
    print(
        json.dumps(
            {
                "output_status": "published",
                "shared_return_rows": report["coverage"]["shared_return_rows"],
                "execution_authority": report["contract"]["execution_authority"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
