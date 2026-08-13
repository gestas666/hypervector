#!/usr/bin/env python3
"""Measure HYPE excursions and screen bounded profit-protection exits."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
    write_immutable_parquet,
)
from hypervector.research.hype_breakout_exit_experiment import (
    split_hype_exit_market,
)
from hypervector.research.hype_breakout_exit_market import (
    build_hype_exit_market,
)
from hypervector.research.hype_breakout_exit_models import HypeExitReplayConfig
from hypervector.research.hype_breakout_profit_research import (
    build_hype_profit_research_bundle,
)

_DEFAULT_BARS = Path("data/cache/HYPE_1m_365d.parquet")
_DEFAULT_FUNDING = Path(
    "data/cache/vendor/hyperliquid/HYPE/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable report-only research command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=_DEFAULT_BARS)
    parser.add_argument("--funding", type=Path, default=_DEFAULT_FUNDING)
    parser.add_argument("--holdout-days", type=int, default=60)
    parser.add_argument("--fold-count", type=int, default=5)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def output_paths(out: Path) -> tuple[Path, Path]:
    """Return the requested summary and derived exact-trade sidecar paths."""
    if out.suffix != ".json":
        raise ValueError("HYPE profit research output must use .json")
    return out, out.with_suffix(".trades.parquet")


def run(args: argparse.Namespace) -> tuple[dict[str, object], pd.DataFrame]:
    """Build source-parity development evidence without opening a new holdout."""
    _require_file(args.bars, "HYPE bars")
    _require_file(args.funding, "HYPE funding")
    raw_bars = pd.read_parquet(args.bars)
    funding = pd.read_parquet(args.funding)
    market, market_evidence = build_hype_exit_market(raw_bars, funding)
    config = HypeExitReplayConfig()
    development, _, split = split_hype_exit_market(
        market,
        config,
        args.holdout_days,
    )
    bundle = build_hype_profit_research_bundle(
        development,
        config=config,
        fold_count=args.fold_count,
    )
    report = bundle.report
    report["source_split"] = split
    report["data_evidence"] = {
        "bars_path": str(args.bars.resolve()),
        "bars": file_evidence(args.bars),
        "funding_path": str(args.funding.resolve()),
        "funding": file_evidence(args.funding),
        "reconstructed_market": asdict(market_evidence),
    }
    return report, bundle.trade_rows


def main() -> None:
    """Publish exact trades first and an immutable hash-linked summary second."""
    args = build_parser().parse_args()
    summary_path, trades_path = output_paths(args.out)
    _require_absent(summary_path)
    _require_absent(trades_path)
    report, trades = run(args)
    write_immutable_parquet(trades_path, trades)
    report["trade_evidence"] = {
        "path": str(trades_path.resolve()),
        **file_evidence(trades_path),
        "rows": len(trades),
    }
    write_immutable_json(summary_path, report)
    print(
        json.dumps(
            {
                "ok": True,
                "summary": str(summary_path),
                "trades": str(trades_path),
                "forward_candidate": report["forward_candidate"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} does not exist: {path}")


def _require_absent(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"immutable HYPE research output exists: {path}")


if __name__ == "__main__":
    main()
