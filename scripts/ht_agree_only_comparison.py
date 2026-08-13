#!/usr/bin/env python3
"""Compare exact HT structural entries with an agree-only challenger."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.ht_agree_only_comparison import (
    build_ht_agree_only_comparison,
)
from hypervector.research.hype_breakout_exit_market import build_hype_exit_market
from hypervector.research.mu_hip3_archive_provenance import (
    require_unchanged_generator,
    source_tree_identity,
)

MarketLoader = Callable[
    [Path, Path], tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]
]


def build_parser() -> argparse.ArgumentParser:
    """Build explicit local-input and immutable-output arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", choices=("BTC", "ETH", "SOL"), required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--funding", type=Path, required=True)
    parser.add_argument("--holdout-days", type=int, default=60)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run_report(
    args: argparse.Namespace,
    *,
    market_loader: MarketLoader | None = None,
) -> dict[str, object]:
    """Build and immutably publish one source-stable comparison artifact."""
    bars = Path(args.bars)
    funding = Path(args.funding)
    _require_file(bars, "HT bars")
    _require_file(funding, "HT funding")
    input_identity = {"bars": file_evidence(bars), "funding": file_evidence(funding)}
    root = Path(__file__).resolve().parents[1]
    generator = source_tree_identity(root, Path(__file__).resolve())
    structural, breakout, market_evidence = (market_loader or _load_markets)(
        bars, funding
    )
    report = build_ht_agree_only_comparison(
        structural,
        breakout,
        symbol=str(args.symbol),
        holdout_days=int(args.holdout_days),
    )
    report["generated_at_utc"] = datetime.now(UTC).isoformat()
    report["evidence"] = {
        "bars": input_identity["bars"],
        "bars_path": str(bars.resolve()),
        "funding": input_identity["funding"],
        "funding_path": str(funding.resolve()),
        "markets": market_evidence,
    }
    report["generator_identity"] = generator
    report = _json_safe(report)
    _require_unchanged_inputs(input_identity, bars, funding)
    require_unchanged_generator(generator, root, Path(__file__).resolve())
    write_immutable_json(Path(args.out), report)
    return report


def _json_safe(report: dict[str, object]) -> dict[str, object]:
    encoded = json.dumps(report, allow_nan=False, sort_keys=True)
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise RuntimeError("HT agree-only report did not encode as an object")
    return decoded


def _load_markets(
    bars: Path,
    funding: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    raw_bars = pd.read_parquet(bars)
    funding_rows = pd.read_parquet(funding)
    structural, structural_evidence = build_hype_exit_market(raw_bars, funding_rows)
    breakout, breakout_evidence = build_hype_exit_market(
        raw_bars,
        funding_rows,
        entry_direction_mode="breakout",
    )
    return (
        structural,
        breakout,
        {
            "structural": asdict(structural_evidence),
            "breakout": asdict(breakout_evidence),
        },
    )


def _require_unchanged_inputs(
    expected: dict[str, dict[str, object]],
    bars: Path,
    funding: Path,
) -> None:
    observed = {"bars": file_evidence(bars), "funding": file_evidence(funding)}
    if observed != expected:
        raise ValueError("HT agree-only input evidence changed during evaluation")


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} does not exist: {path}")


def main() -> int:
    """Publish one immutable report-only comparison and print its delta."""
    args = build_parser().parse_args()
    report = run_report(args)
    holdout = report["holdout_already_opened"]
    if not isinstance(holdout, dict):
        raise RuntimeError("HT agree-only holdout report must be an object")
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(Path(args.out).resolve()),
                "execution_authority": "none",
                "holdout_delta": holdout["challenger_minus_control"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
