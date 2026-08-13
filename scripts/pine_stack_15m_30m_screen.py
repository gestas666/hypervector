#!/usr/bin/env python3
"""Run the immutable report-only four-Pine 15m/30m development control."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.low_tf_multi_asset_contract import (
    complete_ohlcv_bars,
    default_low_tf_contract,
)
from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)
from hypervector.research.pine_stack_features import (
    PineStackFeatureConfig,
    build_pine_stack_features,
)
from hypervector.research.pine_stack_screen import (
    PineStackScreenCell,
    PineStackScreenConfig,
    evaluate_pine_stack_cells,
)
from hypervector.research.pine_stack_screen_journal import PineStackScreenJournal
from hypervector.research.pine_stack_signals import compose_pine_stack_entries

_YEAR_ID = "20250728T000000000000Z_20260728T000000000000Z"


@dataclass(frozen=True)
class PineStackAssetInput:
    """Explicit native-perpetual one-minute and funding source identity."""

    symbol: str
    venue_max_leverage: float
    bars_path: Path
    funding_path: Path


@dataclass(frozen=True)
class PineStackAssetResult:
    """One asset/timeframe source identity and complete trial cells."""

    source_identity: dict[str, object]
    cells: tuple[PineStackScreenCell, ...]


def default_asset_inputs(data_root: Path) -> tuple[PineStackAssetInput, ...]:
    """Return explicit one-year paths for all four native perpetuals."""
    return tuple(
        PineStackAssetInput(
            asset.symbol,
            asset.venue_max_leverage,
            data_root / "cache" / f"{asset.symbol}_1m_365d.parquet",
            data_root
            / "cache"
            / "vendor"
            / "hyperliquid"
            / asset.symbol
            / f"{_YEAR_ID}_funding"
            / "funding.parquet",
        )
        for asset in default_low_tf_contract().assets
    )


def build_parser() -> argparse.ArgumentParser:
    """Return the immutable report-only screen argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--run-id", default="pine_stack_15m_30m_development_v1")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/logs/research/pine_stack_15m_30m_development_v1.json"),
    )
    parser.add_argument(
        "--journal",
        type=Path,
        default=Path("data/research/strategy_trials.duckdb"),
    )
    return parser


def run_development(
    inputs: tuple[PineStackAssetInput, ...],
    *,
    run_id: str,
) -> dict[str, object]:
    """Evaluate source controls on 15m and 30m with identical dates and costs."""
    artifact, _ = _development_artifact(inputs, run_id=run_id)
    return artifact


def _development_artifact(
    inputs: tuple[PineStackAssetInput, ...],
    *,
    run_id: str,
) -> tuple[dict[str, object], tuple[PineStackScreenCell, ...]]:
    contract = default_low_tf_contract()
    start, end = contract.segment("development")
    feature_config = PineStackFeatureConfig()
    screen_config = PineStackScreenConfig()
    results = tuple(
        _evaluate_asset_timeframe(
            asset,
            bar_minutes,
            start,
            end,
            feature_config,
            screen_config,
        )
        for asset in inputs
        for bar_minutes in (15, 30)
    )
    cells = tuple(cell for result in results for cell in result.cells)
    return {
        "schema_version": 1,
        "run_id": run_id,
        "segment": "development",
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "source_identity": [result.source_identity for result in results],
        "feature_config": asdict(feature_config),
        "screen_config": asdict(screen_config),
        "trial_count": len(cells),
        "cells": [_compact_cell(cell) for cell in cells],
        "trade_storage": "DuckDB pine_stack_screen_trades",
        "limitations": [
            "Stage A uses native-bar adverse barrier ordering, not one-minute paths",
            "development results select candidates but cannot promote them",
            "each asset/timeframe/cell has independent 15000 USD starting equity",
        ],
    }, cells


def _compact_cell(cell: PineStackScreenCell) -> dict[str, object]:
    values = asdict(cell)
    values.pop("trade_records")
    return values


def _evaluate_asset_timeframe(
    asset: PineStackAssetInput,
    bar_minutes: int,
    start: pd.Timestamp,
    end: pd.Timestamp,
    feature_config: PineStackFeatureConfig,
    screen_config: PineStackScreenConfig,
) -> PineStackAssetResult:
    minutes = _load_minutes(asset.bars_path)
    native = complete_ohlcv_bars(minutes, source_minutes=1, bar_minutes=bar_minutes)
    features = build_pine_stack_features(
        native, bar_minutes=bar_minutes, config=feature_config
    )
    entries = compose_pine_stack_entries(features, symbol=asset.symbol)
    selected = native["bar_open_at"].ge(start) & native["bar_open_at"].lt(end)
    bars = native.loc[selected].reset_index(drop=True)
    scored_features = features.loc[selected].reset_index(drop=True)
    scored_entries = entries.loc[
        entries["signal_bar_open_at"].ge(start) & entries["decision_time_utc"].lt(end)
    ].reset_index(drop=True)
    _require_exact_native_window(bars, start, end, bar_minutes)
    funding = load_verified_hourly_funding([asset.funding_path], start, end)
    funded = attach_hourly_funding(bars.set_index("bar_open_at"), funding)
    bars = funded.reset_index()
    cells = evaluate_pine_stack_cells(
        bars=bars,
        features=scored_features,
        entries=scored_entries,
        symbol=asset.symbol,
        bar_minutes=bar_minutes,
        venue_max_leverage=asset.venue_max_leverage,
        config=screen_config,
    )
    identity = _source_identity(
        asset, minutes, native, bars, funding, start, bar_minutes
    )
    return PineStackAssetResult(identity, cells)


def _load_minutes(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Pine stack bars do not exist: {path}")
    frame = pd.read_parquet(path)
    required = {"timestamp", "open", "high", "low", "close", "volume", "source"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Pine stack minute bars missing columns: {missing}")
    times = pd.DatetimeIndex(frame["timestamp"])
    if times.tz is None or not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("Pine stack minute bars require ordered unique aware times")
    if not frame["source"].isin({"hl", "hl_gap_fill"}).all():
        raise ValueError("Pine stack bars contain a non-Hyperliquid source")
    return frame.reset_index(drop=True)


def _require_exact_native_window(
    bars: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    bar_minutes: int,
) -> None:
    expected = pd.date_range(start, end, freq=f"{bar_minutes}min", inclusive="left")
    if not pd.DatetimeIndex(bars["bar_open_at"]).equals(expected):
        raise ValueError("Pine stack does not cover the exact native scored window")


def _source_identity(
    asset: PineStackAssetInput,
    minutes: pd.DataFrame,
    native: pd.DataFrame,
    scored: pd.DataFrame,
    funding: pd.Series,
    start: pd.Timestamp,
    bar_minutes: int,
) -> dict[str, object]:
    first = pd.Timestamp(minutes["timestamp"].iloc[0])
    return {
        "symbol": asset.symbol,
        "bar_minutes": bar_minutes,
        "bars_path": str(asset.bars_path.resolve()),
        "bars_sha256": _file_sha256(asset.bars_path),
        "funding_path": str(asset.funding_path.resolve()),
        "funding_sha256": _file_sha256(asset.funding_path),
        "source_minute_rows": len(minutes),
        "source_gap_fill_rows": int(minutes["source"].eq("hl_gap_fill").sum()),
        "native_rows": len(native),
        "scored_rows": len(scored),
        "funding_events": len(funding),
        "leading_warmup_minutes": max(0, int((start - first).total_seconds() // 60)),
        "execution_authority": "none",
    }


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    """Write one immutable development artifact and print its absolute path."""
    args = build_parser().parse_args()
    if args.output.exists():
        raise FileExistsError(f"Pine stack artifact already exists: {args.output}")
    artifact, cells = _development_artifact(
        default_asset_inputs(args.data_root), run_id=args.run_id
    )
    source_identity = artifact.get("source_identity")
    if not isinstance(source_identity, list):
        raise RuntimeError("Pine stack source identity is invalid")
    PineStackScreenJournal(args.journal).write_run(
        run_id=args.run_id,
        segment="development",
        source_identity=tuple(source_identity),
        cells=cells,
    )
    write_immutable_json(args.output, artifact)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
