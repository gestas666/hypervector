#!/usr/bin/env python3
"""Attribute and challenge HYPE breakout entries on development evidence."""

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
from hypervector.research.hype_breakout_entry_attribution import (
    analyze_hype_entry_attribution,
)
from hypervector.research.hype_breakout_entry_features import (
    HYPE_ENTRY_ATTRIBUTION_FEATURES,
    build_hype_entry_features,
    join_hype_entry_outcomes,
)
from hypervector.research.hype_breakout_entry_research import (
    build_hype_entry_research_bundle,
)
from hypervector.research.hype_breakout_exit_experiment import split_hype_exit_market
from hypervector.research.hype_breakout_exit_market import (
    HypeExitMarketEvidence,
    build_hype_exit_market,
)
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
)
from hypervector.research.hype_breakout_exit_replay import replay_hype_breakout_exits

_DEFAULT_BARS = Path("data/cache/HYPE_1m_365d.parquet")
_DEFAULT_FUNDING = Path(
    "data/cache/vendor/hyperliquid/HYPE/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable report-only entry research command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=_DEFAULT_BARS)
    parser.add_argument("--funding", type=Path, default=_DEFAULT_FUNDING)
    parser.add_argument("--holdout-days", type=int, default=60)
    parser.add_argument("--fold-count", type=int, default=5)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def output_paths(out: Path) -> tuple[Path, Path, Path]:
    """Return summary, exact feature, and exact trade output paths."""
    if out.suffix != ".json":
        raise ValueError("HYPE entry research output must use .json")
    return (
        out,
        out.with_suffix(".features.parquet"),
        out.with_suffix(".trades.parquet"),
    )


def run(
    args: argparse.Namespace,
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    """Build development-only entry evidence without reopening the holdout."""
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
    features = build_hype_entry_features(development)
    control = replay_hype_breakout_exits(
        development,
        HypeExitPolicy("hype_breakout_control"),
        config,
    )
    outcomes = join_hype_entry_outcomes(features, control.trades)
    bundle = build_hype_entry_research_bundle(
        development,
        config=config,
        fold_count=args.fold_count,
    )
    report = bundle.report
    report["attribution"] = analyze_hype_entry_attribution(
        outcomes,
        feature_names=HYPE_ENTRY_ATTRIBUTION_FEATURES,
        fold_count=args.fold_count,
        modeled_round_trip_bps=13.0,
    )
    _attach_source_evidence(report, args, split, market_evidence)
    return report, outcomes, bundle.trade_rows


def _attach_source_evidence(
    report: dict[str, object],
    args: argparse.Namespace,
    split: dict[str, object],
    market_evidence: HypeExitMarketEvidence,
) -> None:
    report["source_split"] = split
    report["data_evidence"] = {
        "bars_path": str(args.bars.resolve()),
        "bars": file_evidence(args.bars),
        "funding_path": str(args.funding.resolve()),
        "funding": file_evidence(args.funding),
        "reconstructed_market": asdict(market_evidence),
    }


def main() -> None:
    """Publish exact sidecars first and their hash-linked summary last."""
    args = build_parser().parse_args()
    summary_path, features_path, trades_path = output_paths(args.out)
    for path in (summary_path, features_path, trades_path):
        _require_absent(path)
    report, features, trades = run(args)
    write_immutable_parquet(features_path, features)
    write_immutable_parquet(trades_path, trades)
    report["feature_evidence"] = _sidecar_evidence(features_path, len(features))
    report["trade_evidence"] = _sidecar_evidence(trades_path, len(trades))
    write_immutable_json(summary_path, report)
    print(_completion_json(summary_path, features_path, trades_path, report))


def _sidecar_evidence(path: Path, rows: int) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path), "rows": rows}


def _completion_json(
    summary: Path,
    features: Path,
    trades: Path,
    report: dict[str, object],
) -> str:
    return json.dumps(
        {
            "ok": True,
            "summary": str(summary),
            "features": str(features),
            "trades": str(trades),
            "forward_candidate": report["forward_candidate"],
            "execution_authority": "none",
        },
        sort_keys=True,
    )


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} does not exist: {path}")


def _require_absent(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"immutable HYPE entry research output exists: {path}")


if __name__ == "__main__":
    main()
