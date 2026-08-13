#!/usr/bin/env python3
"""Run immutable development tuning for the four-Pine entry stack."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

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
from hypervector.research.pine_stack_tuning import (
    PineStackTuningConfig,
    PineStackTuningResult,
    declared_entry_parameter_grid,
    declared_final_development_grid,
    declared_pseudo_holdout_grid,
    declared_post_hoc_exit_grid,
    declared_risk_parameter_grid,
    declared_tp_axis_threshold_grid,
    declared_tp_parameter_grid,
    evaluate_pine_stack_tuning_trial,
    rank_pine_stack_tuning_results,
)
from hypervector.research.pine_stack_tuning_journal import (
    PineStackTuningJournal,
)

_YEAR_ID = "20250728T000000000000Z_20260728T000000000000Z"


def build_parser() -> argparse.ArgumentParser:
    """Return the report-only entry-tuning command contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--symbol", choices=("BTC", "ETH", "SOL", "HYPE"), default="ETH"
    )
    parser.add_argument("--bar-minutes", choices=(15, 30), type=int, default=30)
    parser.add_argument(
        "--segment",
        choices=("development", "validation", "pseudo_holdout"),
        default="development",
    )
    parser.add_argument(
        "--surface",
        choices=(
            "entry_v1",
            "risk_hold_v1",
            "tp_support_v1",
            "tp_axis_threshold_v1",
            "final_interaction_v1",
            "frozen_validation_v1",
            "frozen_pseudo_holdout_v1",
            "post_hoc_exit_diagnostic_v1",
        ),
        default="entry_v1",
    )
    parser.add_argument(
        "--run-id", default="pine_stack_eth30_entry_tuning_development_v1"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/logs/research/pine_stack_eth30_entry_tuning_development_v1.json"
        ),
    )
    parser.add_argument(
        "--journal",
        type=Path,
        default=Path("data/research/strategy_trials.duckdb"),
    )
    return parser


def main() -> int:
    """Evaluate, journal, and publish the complete report-only surface."""
    args = build_parser().parse_args()
    _validate_protocol(args.surface, args.segment)
    segment = _segment_name(args.segment)
    if args.output.exists():
        raise FileExistsError(f"Pine tuning artifact already exists: {args.output}")
    bars_path, funding_path = _source_paths(args.data_root, args.symbol)
    feature_bars, scored_bars, source_identity = _load_inputs(
        bars_path, funding_path, args.symbol, args.bar_minutes, segment
    )
    parameters = _surface_parameters(args.surface)
    source_identity["surface"] = args.surface
    results = tuple(
        evaluate_pine_stack_tuning_trial(
            feature_bars=feature_bars,
            scored_bars=scored_bars,
            symbol=args.symbol,
            venue_max_leverage=_venue_max_leverage(args.symbol),
            bar_minutes=args.bar_minutes,
            config=config,
        )
        for config in parameters
    )
    summaries = rank_pine_stack_tuning_results(results)
    PineStackTuningJournal(args.journal).write_run(
        run_id=args.run_id,
        segment=segment,
        source_identity=source_identity,
        results=results,
        summaries=summaries,
    )
    artifact = _artifact(args, source_identity, results, summaries)
    write_immutable_json(args.output, artifact)
    print(args.output.resolve())
    return 0


def _source_paths(data_root: Path, symbol: str) -> tuple[Path, Path]:
    bars = data_root / "cache" / f"{symbol}_1m_365d.parquet"
    funding = (
        data_root
        / "cache"
        / "vendor"
        / "hyperliquid"
        / symbol
        / f"{_YEAR_ID}_funding"
        / "funding.parquet"
    )
    return bars, funding


def _surface_parameters(surface: str) -> tuple[PineStackTuningConfig, ...]:
    surfaces = {
        "entry_v1": declared_entry_parameter_grid,
        "risk_hold_v1": declared_risk_parameter_grid,
        "tp_support_v1": declared_tp_parameter_grid,
        "tp_axis_threshold_v1": declared_tp_axis_threshold_grid,
        "final_interaction_v1": declared_final_development_grid,
        "frozen_validation_v1": declared_final_development_grid,
        "frozen_pseudo_holdout_v1": declared_pseudo_holdout_grid,
        "post_hoc_exit_diagnostic_v1": declared_post_hoc_exit_grid,
    }
    return surfaces[surface]()


def _validate_protocol(surface: str, segment: str) -> None:
    if surface == "post_hoc_exit_diagnostic_v1":
        return
    if segment == "validation" and surface != "frozen_validation_v1":
        raise ValueError("validation requires the pre-frozen frozen_validation_v1")
    if segment == "pseudo_holdout" and surface != "frozen_pseudo_holdout_v1":
        raise ValueError(
            "pseudo-holdout requires the pre-frozen frozen_pseudo_holdout_v1"
        )
    if segment == "development" and surface.startswith("frozen_"):
        raise ValueError("frozen validation surfaces require later segments")


def _segment_name(value: str) -> SegmentName:
    if value not in {"development", "validation", "pseudo_holdout"}:
        raise ValueError(f"unsupported Pine tuning segment: {value}")
    return cast(SegmentName, value)


def _load_inputs(
    bars_path: Path,
    funding_path: Path,
    symbol: str,
    bar_minutes: int,
    segment: SegmentName,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    minutes = _load_minutes(bars_path)
    native = complete_ohlcv_bars(minutes, source_minutes=1, bar_minutes=bar_minutes)
    start, end = default_low_tf_contract().segment(segment)
    feature_bars = native.loc[native["bar_open_at"].lt(end)].reset_index(drop=True)
    selected = native["bar_open_at"].ge(start) & native["bar_open_at"].lt(end)
    scored = native.loc[selected].reset_index(drop=True)
    _require_exact_window(scored, start, end, bar_minutes)
    funding = load_verified_hourly_funding([funding_path], start, end)
    scored = attach_hourly_funding(
        scored.set_index("bar_open_at"), funding
    ).reset_index()
    identity = {
        "symbol": symbol,
        "bar_minutes": bar_minutes,
        "bars_path": str(bars_path.resolve()),
        "bars_evidence": file_evidence(bars_path),
        "funding_path": str(funding_path.resolve()),
        "funding_evidence": file_evidence(funding_path),
        "source_minute_rows": len(minutes),
        "source_gap_fill_rows": int(minutes["source"].eq("hl_gap_fill").sum()),
        "feature_rows": len(feature_bars),
        "scored_rows": len(scored),
        "funding_events": len(funding),
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
    }
    return feature_bars, scored, identity


def _load_minutes(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Pine tuning bars do not exist: {path}")
    frame = pd.read_parquet(path)
    required = {"timestamp", "open", "high", "low", "close", "volume", "source"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Pine tuning minute bars missing columns: {missing}")
    times = pd.DatetimeIndex(frame["timestamp"])
    if times.tz is None or not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("Pine tuning bars require ordered unique aware timestamps")
    if not frame["source"].isin({"hl", "hl_gap_fill"}).all():
        raise ValueError("Pine tuning bars contain a non-Hyperliquid source")
    return frame.reset_index(drop=True)


def _require_exact_window(
    bars: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    bar_minutes: int,
) -> None:
    expected = pd.date_range(start, end, freq=f"{bar_minutes}min", inclusive="left")
    if not pd.DatetimeIndex(bars["bar_open_at"]).equals(expected):
        raise ValueError("Pine tuning does not cover the exact development window")


def _venue_max_leverage(symbol: str) -> float:
    values = {
        asset.symbol: asset.venue_max_leverage
        for asset in default_low_tf_contract().assets
    }
    return values[symbol]


def _artifact(
    args: argparse.Namespace,
    source_identity: dict[str, object],
    results: tuple[PineStackTuningResult, ...],
    summaries: tuple[object, ...],
) -> dict[str, object]:
    return {
        "schema_version": "pine_stack_entry_tuning_v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "run_id": args.run_id,
        "segment": args.segment,
        "surface": args.surface,
        "report_only": True,
        "execution_authority": "none",
        "source_identity": source_identity,
        "parameters": [asdict(result.config) for result in results],
        "summaries": [asdict(value) for value in summaries],
        "results": [_compact_result(result) for result in results],
        "trade_storage": "DuckDB pine_stack_tuning_trades",
        "limitations": [
            "development tuning cannot promote a candidate",
            "native-bar adverse barrier ordering is not one-minute path replay",
            "ranking is advisory and retains all losing trials",
        ],
    }


def _compact_result(result: PineStackTuningResult) -> dict[str, object]:
    payload = asdict(result)
    payload.pop("trade_records")
    payload["trial_id"] = result.config.trial_id
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
