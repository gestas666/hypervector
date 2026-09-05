#!/usr/bin/env python3
"""Publish exact aligned-entry HYPE fixed-target sensitivity evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    verify_file_evidence,
    write_immutable_json,
)
from hypervector.research.hype_breakout_exit_experiment import split_hype_exit_market
from hypervector.research.hype_breakout_exit_market import build_hype_exit_market
from hypervector.research.hype_breakout_exit_models import HypeExitReplayConfig
from hypervector.research.hype_fixed_target_sensitivity import (
    TARGET_EXIT_TAIL_SLIPPAGE_BPS,
    TARGET_GRID_BPS,
    build_fixed_target_report,
)

_ROOT = Path(__file__).resolve().parents[1]
_BASELINE = _ROOT / (
    "data/logs/research/hype_compression_breakout_challenger_20260816_v6_alignment"
)
_DEVELOPMENT_BARS = _ROOT / "data/cache/HYPE_1m_365d.parquet"
_DEVELOPMENT_FUNDING = _ROOT / (
    "data/cache/vendor/hyperliquid/HYPE/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)
_CONFIRMATION_CANDLES = _ROOT / (
    "data/cache/vendor/0xarchive/hyperliquid/HYPE/"
    "20260728T000000000000Z_20260810T234500000000Z_candles_1m/candles.parquet"
)
_CONFIRMATION_FUNDING = _ROOT / (
    "data/cache/vendor/hyperliquid/HYPE/"
    "20260728T000000000000Z_20260811T000000000000Z_funding/funding.parquet"
)
_POLICY_ID = "compression_5m50_1m40_pullback"


class _Inputs(NamedTuple):
    """Verified markets, lifecycle rows, and split evidence."""

    development: pd.DataFrame
    development_trades: pd.DataFrame
    confirmation: tuple[tuple[pd.DataFrame, pd.DataFrame], ...]
    split: dict[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=_BASELINE)
    parser.add_argument("--development-bars", type=Path, default=_DEVELOPMENT_BARS)
    parser.add_argument(
        "--development-funding", type=Path, default=_DEVELOPMENT_FUNDING
    )
    parser.add_argument(
        "--confirmation-candles", type=Path, default=_CONFIRMATION_CANDLES
    )
    parser.add_argument(
        "--confirmation-funding", type=Path, default=_CONFIRMATION_FUNDING
    )
    parser.add_argument("--fold-count", type=int, default=5)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def execution_config() -> HypeExitReplayConfig:
    """Return the exact live-v52 HYPE execution assumptions."""
    return HypeExitReplayConfig(
        stop_bps=80.0,
        maximum_hold_minutes=480,
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_minutes=1_440,
        exit_on_opposite_signal=True,
    )


def verified_baseline(directory: Path) -> dict[str, object]:
    """Load a complete v6 alignment baseline after checksum verification."""
    manifest = _json_object(directory / "manifest.json")
    files = manifest.get("files")
    if manifest.get("complete") is not True or not isinstance(files, dict):
        raise ValueError("HYPE alignment baseline evidence is incomplete")
    verify_file_evidence(directory, files)
    required = {
        "report.json",
        "alignment_development_trades.parquet",
        "alignment_confirmation_trades.parquet",
    }
    if not required.issubset(files):
        raise ValueError("HYPE alignment baseline omits required sidecars")
    report = _json_object(directory / "report.json")
    alignment = _object(report.get("compression_alignment_replay"), "alignment")
    contract = _object(alignment.get("contract"), "alignment contract")
    if contract.get("frozen_compression_policy_id") != _POLICY_ID:
        raise ValueError("HYPE alignment policy identity is inconsistent")
    if alignment.get("execution_authority") != "none":
        raise ValueError("HYPE alignment baseline grants execution authority")
    return report


def selected_trades(
    frame: pd.DataFrame, *, expected: int, confirmation: bool
) -> pd.DataFrame:
    """Select only the exact aligned cohort and validate its population."""
    required = {
        "cohort",
        "side",
        "entry_time_utc",
        "exit_time_utc",
        "entry_price",
        "net_return_bps",
        "exit_reason",
    }
    if required - set(frame.columns):
        raise ValueError("HYPE alignment lifecycle sidecar is incomplete")
    selected = frame.loc[frame["cohort"].eq("aligned_only")].copy()
    if len(selected) != expected:
        raise ValueError("HYPE aligned lifecycle count does not match baseline")
    if confirmation:
        _validate_confirmation_rows(selected)
    return selected


def run(args: argparse.Namespace) -> dict[str, object]:
    """Build and publish one immutable authority-free sensitivity report."""
    if args.out.exists():
        raise FileExistsError(f"immutable HYPE fixed-target report exists: {args.out}")
    baseline = verified_baseline(args.baseline)
    source_snapshot = _source_snapshot(args)
    generator = _generator_identity()
    inputs = _inputs(args, baseline)
    report = build_fixed_target_report(
        inputs.development,
        inputs.development_trades,
        inputs.confirmation,
        target_grid_bps=TARGET_GRID_BPS,
        config=execution_config(),
        development_fold_count=args.fold_count,
        target_exit_tail_slippage_bps=TARGET_EXIT_TAIL_SLIPPAGE_BPS,
    )
    report.update(_provenance(inputs.split, source_snapshot, generator))
    _require_unchanged(source_snapshot)
    _require_unchanged(generator)
    write_immutable_json(args.out, report)
    return report


def _inputs(args: argparse.Namespace, baseline: dict[str, object]) -> _Inputs:
    _verify_source_inputs(args, baseline)
    market, _ = build_hype_exit_market(
        pd.read_parquet(args.development_bars),
        pd.read_parquet(args.development_funding),
    )
    development, _sealed, split = split_hype_exit_market(market, execution_config(), 60)
    if split != baseline.get("development_split"):
        raise ValueError("HYPE alignment development split changed")
    development_count, confirmation_count = _expected_counts(baseline)
    development_trades = selected_trades(
        pd.read_parquet(args.baseline / "alignment_development_trades.parquet"),
        expected=development_count,
        confirmation=False,
    )
    confirmation = _confirmation_periods(args, confirmation_count)
    return _Inputs(development, development_trades, confirmation, split)


def _confirmation_periods(
    args: argparse.Namespace, expected: int
) -> tuple[tuple[pd.DataFrame, pd.DataFrame], ...]:
    raw = pd.read_parquet(args.confirmation_candles)
    funding = pd.read_parquet(args.confirmation_funding)
    trades = selected_trades(
        pd.read_parquet(args.baseline / "alignment_confirmation_trades.parquet"),
        expected=expected,
        confirmation=True,
    )
    output: list[tuple[pd.DataFrame, pd.DataFrame]] = []
    for number, segment in enumerate(_continuous_segments(raw), start=1):
        selected = trades.loc[trades["segment"].eq(number)]
        if not selected.empty:
            market, _ = build_hype_exit_market(segment, funding)
            output.append((market, selected))
    if sum(len(rows) for _, rows in output) != expected:
        raise ValueError("HYPE aligned confirmation rows do not map to segments")
    return tuple(output)


def _continuous_segments(raw: pd.DataFrame) -> tuple[pd.DataFrame, ...]:
    if "timestamp" not in raw:
        raise ValueError("HYPE confirmation candles require timestamp")
    timestamps = pd.to_datetime(raw["timestamp"], utc=True)
    if timestamps.duplicated().any() or not timestamps.is_monotonic_increasing:
        raise ValueError("HYPE confirmation timestamps must be ordered and unique")
    groups = timestamps.diff().ne(pd.Timedelta(minutes=1)).cumsum()
    return tuple(part.copy() for _, part in raw.groupby(groups, sort=False))


def _expected_counts(report: dict[str, object]) -> tuple[int, int]:
    alignment = _object(report.get("compression_alignment_replay"), "alignment")
    development = _object(alignment.get("development"), "development")
    confirmation = _object(alignment.get("later_confirmation"), "confirmation")
    development_row = _object(development.get("aligned_only"), "development aligned")
    confirmation_row = _object(confirmation.get("aligned_only"), "confirmation aligned")
    return (
        _positive_integer(development_row.get("completed_trades"), "development"),
        _positive_integer(confirmation_row.get("completed_trades"), "confirmation"),
    )


def _validate_confirmation_rows(frame: pd.DataFrame) -> None:
    if {"segment", "censored"} - set(frame.columns):
        raise ValueError("HYPE aligned confirmation lacks segment identity")
    if frame["censored"].any():
        raise ValueError("HYPE aligned confirmation contains censored lifecycle")


def _verify_source_inputs(args: argparse.Namespace, report: dict[str, object]) -> None:
    source = _object(report.get("source_evidence"), "source evidence")
    for key, path in (
        ("development_bars", args.development_bars),
        ("development_funding", args.development_funding),
    ):
        expected = _object(source.get(key), key)
        if file_evidence(path) != {
            name: expected[name] for name in ("bytes", "sha256")
        }:
            raise ValueError(f"HYPE {key} evidence changed")
    _verify_manifest_source(
        source, "confirmation_candle_manifest", args.confirmation_candles
    )
    _verify_manifest_source(
        source, "confirmation_funding_manifest", args.confirmation_funding
    )


def _verify_manifest_source(
    source: dict[str, object], key: str, data_path: Path
) -> None:
    reference = _object(source.get(key), key)
    payload = _object(reference.get("payload"), f"{key} payload")
    files = _object(payload.get("files"), f"{key} files")
    expected = _object(files.get(data_path.name), f"{key} data file")
    if file_evidence(data_path) != {
        name: expected[name] for name in ("bytes", "sha256")
    }:
        raise ValueError(f"HYPE {key} evidence changed")


def _source_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    return (
        args.baseline / "manifest.json",
        args.baseline / "report.json",
        args.baseline / "alignment_development_trades.parquet",
        args.baseline / "alignment_confirmation_trades.parquet",
        args.development_bars,
        args.development_funding,
        args.confirmation_candles,
        args.confirmation_funding,
    )


def _source_snapshot(args: argparse.Namespace) -> dict[str, dict[str, object]]:
    return {str(path.resolve()): file_evidence(path) for path in _source_paths(args)}


def _generator_identity() -> dict[str, dict[str, object]]:
    relative = (
        "scripts/hype_aligned_fixed_target_sensitivity.py",
        "src/hypervector/research/hype_fixed_target_sensitivity.py",
        "src/hypervector/research/hype_mature_profit_floor_sensitivity.py",
        "src/hypervector/research/hype_breakout_exit_market.py",
        "src/hypervector/research/hype_breakout_exit_experiment.py",
        "src/hypervector/research/hype_breakout_exit_models.py",
        "src/hypervector/cohort_profit_lock_policy.py",
        "src/hypervector/research/cohort_trade_reflection_index.py",
    )
    paths = tuple(_ROOT / path for path in relative)
    return {str(path.resolve()): file_evidence(path) for path in paths}


def _provenance(
    split: dict[str, object],
    sources: dict[str, dict[str, object]],
    generator: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "frozen_entry_policy_id": _POLICY_ID,
        "frozen_entry_cohort": "aligned_only",
        "development_split": split,
        "source_evidence": sources,
        "generator_identity": generator,
    }


def _require_unchanged(expected: dict[str, dict[str, object]]) -> None:
    observed = {path: file_evidence(Path(path)) for path in expected}
    if observed != expected:
        raise RuntimeError("HYPE fixed-target evidence changed during evaluation")


def _json_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(
            f"required HYPE fixed-target evidence is absent: {path}"
        )
    return _object(json.loads(path.read_text(encoding="utf-8")), str(path))


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} evidence must be an object")
    return value


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"HYPE {label} aligned count must be positive")
    return value


def main() -> None:
    """Publish one immutable report without strategy or execution authority."""
    args = build_parser().parse_args()
    report = run(args)
    selection = _object(report.get("selection"), "selection")
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.out),
                "selected_target_bps": selection["selected_target_bps"],
                "disposition": report["disposition"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
