#!/usr/bin/env python3
"""Replay the development-selected SOL 30m Pine route on later windows."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.low_tf_multi_asset_contract import (
    SegmentName,
    complete_ohlcv_bars,
    default_low_tf_contract,
)
from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)
from hypervector.research.pine_stack_features import build_pine_stack_features
from hypervector.research.pine_stack_frozen_route import (
    FrozenPinePartitionResult,
    evaluate_frozen_pine_partition,
    frozen_sol30_route,
)
from hypervector.research.pine_stack_screen import PineStackScreenConfig
from hypervector.research.pine_stack_signals import compose_pine_stack_entries

Partition = Literal["validation", "pseudo_holdout"]
_PARTITIONS: tuple[Partition, ...] = ("validation", "pseudo_holdout")
_ROUTE = frozen_sol30_route()
_YEAR_ID = "20250728T000000000000Z_20260728T000000000000Z"
_DEVELOPMENT = Path("data/logs/research/pine_stack_15m_30m_development_v1_summary.json")


def build_parser() -> argparse.ArgumentParser:
    """Return a fixed-identity, report-only replay command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/logs/research/pine_stack_sol30_frozen_later_windows_v1.json"
        ),
    )
    return parser


def main() -> int:
    """Evaluate both predeclared later windows and publish immutable evidence."""
    args = build_parser().parse_args()
    if args.output.exists():
        raise FileExistsError(f"frozen SOL Pine output already exists: {args.output}")
    project_root = Path(__file__).resolve().parents[1]
    generator = _generator_identity(project_root)
    sources = _source_paths(args.data_root)
    evidence = _source_evidence(project_root, sources)
    partitions = _evaluate_partitions(sources)
    _require_unchanged(project_root, generator, sources, evidence)
    artifact = _artifact(generator, evidence, partitions)
    write_immutable_json(args.output, artifact)
    print(args.output.resolve())
    return 0


def _source_paths(data_root: Path) -> dict[str, Path]:
    return {
        "bars": data_root / "cache/SOL_1m_365d.parquet",
        "funding": data_root
        / "cache/vendor/hyperliquid/SOL"
        / f"{_YEAR_ID}_funding/funding.parquet",
        "development": _DEVELOPMENT,
    }


def _source_evidence(
    project_root: Path,
    sources: dict[str, Path],
) -> dict[str, dict[str, object]]:
    evidence: dict[str, dict[str, object]] = {}
    for name, path in sources.items():
        resolved = path if path.is_absolute() else project_root / path
        if not resolved.is_file():
            raise FileNotFoundError(f"frozen SOL Pine source is missing: {resolved}")
        evidence[name] = {"path": str(resolved), **file_evidence(resolved)}
    return evidence


def _evaluate_partitions(
    sources: dict[str, Path],
) -> dict[str, dict[str, object]]:
    minutes = _load_minutes(sources["bars"])
    native = complete_ohlcv_bars(
        minutes, source_minutes=1, bar_minutes=_ROUTE.bar_minutes
    )
    features = build_pine_stack_features(native, bar_minutes=_ROUTE.bar_minutes)
    entries = compose_pine_stack_entries(features, symbol=_ROUTE.symbol)
    return {
        partition: _evaluate_partition(
            partition, native, features, entries, sources["funding"]
        )
        for partition in _PARTITIONS
    }


def _evaluate_partition(
    partition: Partition,
    native: pd.DataFrame,
    features: pd.DataFrame,
    entries: pd.DataFrame,
    funding_path: Path,
) -> dict[str, object]:
    start, end = default_low_tf_contract().segment(_segment(partition))
    selected = native["bar_open_at"].ge(start) & native["bar_open_at"].lt(end)
    bars = native.loc[selected].reset_index(drop=True)
    scored_features = features.loc[selected].reset_index(drop=True)
    scored_entries = _partition_entries(entries, start, end)
    _require_exact_window(bars, start, end)
    funding = load_verified_hourly_funding([funding_path], start, end)
    bars = attach_hourly_funding(bars.set_index("bar_open_at"), funding).reset_index()
    result = _evaluate_route(bars, scored_features, scored_entries)
    return {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "native_rows": len(bars),
        "funding_events": len(funding),
        **result.to_dict(),
    }


def _partition_entries(
    entries: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    selected = entries["signal_bar_open_at"].ge(start) & entries[
        "decision_time_utc"
    ].lt(end)
    return entries.loc[selected].reset_index(drop=True)


def _evaluate_route(
    bars: pd.DataFrame,
    features: pd.DataFrame,
    entries: pd.DataFrame,
) -> FrozenPinePartitionResult:
    venue_max = next(
        asset.venue_max_leverage
        for asset in default_low_tf_contract().assets
        if asset.symbol == _ROUTE.symbol
    )
    return evaluate_frozen_pine_partition(
        bars=bars,
        features=features,
        entries=entries,
        route=_ROUTE,
        venue_max_leverage=venue_max,
        nominal_config=PineStackScreenConfig(),
        stress_config=PineStackScreenConfig(
            maker_target_fee_rate=0.00045,
            slippage_bps_per_side=5.0,
        ),
    )


def _load_minutes(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"frozen SOL Pine bars do not exist: {path}")
    frame = pd.read_parquet(path)
    required = {"timestamp", "open", "high", "low", "close", "volume", "source"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"frozen SOL Pine minute bars missing columns: {missing}")
    times = pd.DatetimeIndex(frame["timestamp"])
    if times.tz is None or not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("frozen SOL Pine minute bars require ordered aware times")
    if not frame["source"].isin({"hl", "hl_gap_fill"}).all():
        raise ValueError("frozen SOL Pine bars contain an unsupported source")
    return frame.reset_index(drop=True)


def _require_exact_window(
    bars: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> None:
    expected = pd.date_range(
        start, end, freq=f"{_ROUTE.bar_minutes}min", inclusive="left"
    )
    if not pd.DatetimeIndex(bars["bar_open_at"]).equals(expected):
        raise ValueError("frozen SOL Pine replay lacks exact partition coverage")


def _segment(partition: Partition) -> SegmentName:
    return cast(SegmentName, partition)


def _artifact(
    generator: dict[str, object],
    evidence: dict[str, dict[str, object]],
    partitions: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": "pine_stack_sol30_frozen_later_windows_v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "selection": {
            "route": asdict(_ROUTE),
            "selected_before_later_windows": True,
            "development_search_cells": 192,
            "development_artifact": evidence["development"],
        },
        "cost_contract": {
            "nominal": asdict(PineStackScreenConfig()),
            "stress": asdict(
                PineStackScreenConfig(
                    maker_target_fee_rate=0.00045,
                    slippage_bps_per_side=5.0,
                )
            ),
        },
        "partitions": partitions,
        "source_evidence": evidence,
        "generator_identity": generator,
        "limitations": [
            "native-bar replay does not reconstruct one-minute barrier ordering",
            "the development search examined 192 cells before this identity was frozen",
            "later-window results diagnose this identity and grant no live authority",
        ],
    }


def _generator_identity(project_root: Path) -> dict[str, object]:
    relative_paths = (
        Path("scripts/pine_stack_sol30_frozen_replay.py"),
        Path("src/hypervector/research/pine_stack_frozen_route.py"),
        Path("src/hypervector/research/pine_stack_features.py"),
        Path("src/hypervector/research/pine_stack_signals.py"),
        Path("src/hypervector/research/pine_stack_portfolio_adapter.py"),
        Path("src/hypervector/research/pine_stack_screen.py"),
        Path("src/hypervector/research/shared_bar_portfolio.py"),
        Path("src/hypervector/research/shared_portfolio_models.py"),
        Path("src/hypervector/research/low_tf_multi_asset_contract.py"),
        Path("src/hypervector/research/market_cipher_data.py"),
        Path("pyproject.toml"),
        Path("uv.lock"),
    )
    return {str(path): file_evidence(project_root / path) for path in relative_paths}


def _require_unchanged(
    project_root: Path,
    generator: dict[str, object],
    sources: dict[str, Path],
    evidence: dict[str, dict[str, object]],
) -> None:
    if _generator_identity(project_root) != generator:
        raise RuntimeError("frozen SOL Pine generator changed during replay")
    observed = _source_evidence(project_root, sources)
    if observed != evidence:
        raise RuntimeError("frozen SOL Pine input evidence changed during replay")


if __name__ == "__main__":
    raise SystemExit(main())
