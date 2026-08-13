#!/usr/bin/env python3
"""Run the immutable multi-asset low-timeframe research matrix."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.low_tf_multi_asset_contract import default_low_tf_contract
from hypervector.research.low_tf_multi_asset_features import LowTfFeatureConfig
from hypervector.research.low_tf_multi_asset_replay_models import LowTfReplayConfig
from hypervector.research.low_tf_multi_asset_screen import (
    LowTfAssetWindowRun,
    LowTfScreenAssetInput,
    LowTfScreenCell,
    ScreenSegment,
    build_low_tf_screen_artifact,
    evaluate_low_tf_asset_window,
)
from hypervector.research.low_tf_multi_asset_screen_journal import (
    LowTfScreenJournal,
)
from hypervector.research.low_tf_multi_asset_signals import LowTfSignalConfig

_YEAR_ID = "20250728T000000000000Z_20260728T000000000000Z"


def default_asset_inputs(data_root: Path) -> tuple[LowTfScreenAssetInput, ...]:
    """Return explicit one-year venue bar and funding paths for all assets."""
    contract = default_low_tf_contract()
    return tuple(
        LowTfScreenAssetInput(
            symbol=asset.symbol,
            venue_max_leverage=asset.venue_max_leverage,
            bars_path=data_root / "cache" / f"{asset.symbol}_1m_365d.parquet",
            funding_paths=(
                data_root
                / "cache"
                / "vendor"
                / "hyperliquid"
                / asset.symbol
                / f"{_YEAR_ID}_funding"
                / "funding.parquet",
            ),
        )
        for asset in contract.assets
    )


def build_parser() -> argparse.ArgumentParser:
    """Return the report-only low-timeframe screen argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--segment",
        choices=("development", "validation", "pseudo_holdout"),
        default="development",
    )
    parser.add_argument("--run-id", default="low_tf_multi_asset_development_v1")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/logs/research/low_tf_multi_asset_development_v1.json"),
    )
    parser.add_argument(
        "--journal",
        type=Path,
        default=Path("data/research/strategy_trials.duckdb"),
    )
    return parser


def run_segment(
    *,
    inputs: tuple[LowTfScreenAssetInput, ...],
    segment: ScreenSegment,
    run_id: str,
) -> tuple[dict[str, object], tuple[LowTfScreenCell, ...]]:
    """Evaluate the declared segment for all assets without execution authority."""
    contract = default_low_tf_contract()
    start, end = contract.segment(segment)
    base_replay = LowTfReplayConfig(
        initial_equity=contract.initial_equity_usd,
        risk_fraction=contract.risk_fraction_per_trade,
        leverage=contract.leverage,
        round_trip_cost_bps=contract.nominal_round_trip_cost_bps,
    )
    runs = tuple(
        _evaluate_asset(
            value,
            start,
            end,
            segment,
            replace(base_replay, venue_max_leverage=value.venue_max_leverage),
        )
        for value in inputs
    )
    artifact = build_low_tf_screen_artifact(
        run_id=run_id,
        segment=segment,
        start=start,
        end=end,
        asset_runs=runs,
    )
    cells = tuple(cell for run in runs for cell in run.cells)
    return artifact, cells


def _evaluate_asset(
    asset: LowTfScreenAssetInput,
    start: pd.Timestamp,
    end: pd.Timestamp,
    segment: ScreenSegment,
    replay: LowTfReplayConfig,
) -> LowTfAssetWindowRun:
    """Evaluate one asset using the frozen default feature and signal rules."""
    return evaluate_low_tf_asset_window(
        asset=asset,
        start=start,
        end=end,
        segment=segment,
        feature_config=LowTfFeatureConfig(),
        signal_config=LowTfSignalConfig(),
        replay_config=replay,
    )


def main() -> int:
    """Persist one immutable JSON summary and complete DuckDB trade ledger."""
    args = build_parser().parse_args()
    if args.output.exists():
        raise FileExistsError(f"screen artifact already exists: {args.output}")
    artifact, cells = run_segment(
        inputs=default_asset_inputs(args.data_root),
        segment=args.segment,
        run_id=args.run_id,
    )
    source_identity = artifact.get("source_identity")
    if not isinstance(source_identity, dict):
        raise RuntimeError("screen artifact source identity is invalid")
    LowTfScreenJournal(args.journal).write_run(
        run_id=args.run_id,
        segment=args.segment,
        source_identity=source_identity,
        cells=cells,
    )
    write_immutable_json(args.output, artifact)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
