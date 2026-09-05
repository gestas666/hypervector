#!/usr/bin/env python3
"""Publish fixed-entry HYPE mature-profit-floor sensitivity evidence."""

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
from hypervector.research.cohort_mature_profit_floor import (
    MATURE_PROFIT_FLOOR_POLICIES,
)
from hypervector.research.hype_breakout_exit_experiment import split_hype_exit_market
from hypervector.research.hype_breakout_exit_market import build_hype_exit_market
from hypervector.research.hype_breakout_exit_models import HypeExitReplayConfig
from hypervector.research.hype_mature_profit_floor_sensitivity import (
    build_hype_mature_profit_floor_report,
)

_ROOT = Path(__file__).resolve().parents[1]
_BASELINE = _ROOT / (
    "data/logs/research/"
    "hype_compression_breakout_challenger_20260814_v5_live_exit_parity"
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
    """Verified exact markets and lifecycle rows for the sensitivity."""

    development: pd.DataFrame
    development_trades: pd.DataFrame
    confirmation: tuple[tuple[pd.DataFrame, pd.DataFrame], ...]
    split: dict[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only immutable command parser."""
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
    """Return the exact v51 HYPE execution assumptions used by the baseline."""
    return HypeExitReplayConfig(
        stop_bps=80.0,
        maximum_hold_minutes=480,
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_minutes=1_440,
        exit_on_opposite_signal=True,
    )


def verified_baseline(directory: Path) -> dict[str, object]:
    """Load one complete baseline after verifying every declared file."""
    manifest_path = directory / "manifest.json"
    manifest = _json_object(manifest_path)
    files = manifest.get("files")
    if manifest.get("complete") is not True or not isinstance(files, dict):
        raise ValueError("HYPE baseline evidence manifest is incomplete")
    verify_file_evidence(directory, files)
    required = {
        "report.json",
        "development_trades.parquet",
        "confirmation_trades.parquet",
    }
    if not required.issubset(files):
        raise ValueError("HYPE baseline evidence omits required sidecars")
    report = _json_object(directory / "report.json")
    selection = _object(
        _object(report.get("development"), "development").get("selection"), "selection"
    )
    if selection.get("selected_challenger") != _POLICY_ID:
        raise ValueError("HYPE baseline selected policy is inconsistent")
    return report


def run(args: argparse.Namespace) -> dict[str, object]:
    """Build sensitivity while keeping development and confirmation separate."""
    if args.out.exists():
        raise FileExistsError(f"immutable HYPE floor report exists: {args.out}")
    baseline = verified_baseline(args.baseline)
    generator = _generator_identity()
    inputs = _inputs(args, baseline)
    report = build_hype_mature_profit_floor_report(
        inputs.development,
        inputs.development_trades,
        inputs.confirmation,
        policy=MATURE_PROFIT_FLOOR_POLICIES[0],
        config=execution_config(),
        development_fold_count=args.fold_count,
    )
    report.update(_provenance(args, baseline, inputs.split, generator))
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
    development_trades = _selected_trades(
        pd.read_parquet(args.baseline / "development_trades.parquet"),
        confirmation=False,
    )
    confirmation = _confirmation_periods(args)
    return _Inputs(development, development_trades, confirmation, split)


def _confirmation_periods(
    args: argparse.Namespace,
) -> tuple[tuple[pd.DataFrame, pd.DataFrame], ...]:
    raw = pd.read_parquet(args.confirmation_candles)
    funding = pd.read_parquet(args.confirmation_funding)
    segments = _continuous_candle_segments(raw)
    trades = _selected_trades(
        pd.read_parquet(args.baseline / "confirmation_trades.parquet"),
        confirmation=True,
    )
    output: list[tuple[pd.DataFrame, pd.DataFrame]] = []
    for number, segment in enumerate(segments, start=1):
        selected = trades.loc[trades["segment"].eq(number)]
        if selected.empty:
            continue
        market, _ = build_hype_exit_market(segment, funding)
        output.append((market, selected))
    if not output or sum(len(rows) for _, rows in output) != len(trades):
        raise ValueError("HYPE confirmation trades do not map to exact segments")
    return tuple(output)


def _continuous_candle_segments(raw: pd.DataFrame) -> tuple[pd.DataFrame, ...]:
    if "timestamp" not in raw:
        raise ValueError("HYPE confirmation candles require timestamp")
    timestamps = pd.to_datetime(raw["timestamp"], utc=True)
    if timestamps.duplicated().any() or not timestamps.is_monotonic_increasing:
        raise ValueError("HYPE confirmation timestamps must be ordered and unique")
    groups = timestamps.diff().ne(_minute()).cumsum()
    return tuple(part.copy() for _, part in raw.groupby(groups, sort=False))


def _minute() -> pd.Timedelta:
    return pd.Timedelta(minutes=1)


def _selected_trades(frame: pd.DataFrame, *, confirmation: bool) -> pd.DataFrame:
    required = {
        "policy_id",
        "side",
        "entry_time_utc",
        "exit_time_utc",
        "entry_price",
        "net_return_bps",
        "exit_reason",
    }
    if required - set(frame.columns):
        raise ValueError("HYPE baseline trade sidecar is incomplete")
    selected = frame.loc[frame["policy_id"].eq(_POLICY_ID)].copy()
    if confirmation:
        if {"segment", "censored"} - set(selected.columns):
            raise ValueError("HYPE confirmation sidecar lacks segment identity")
        if selected["censored"].any():
            raise ValueError("HYPE confirmation has censored selected lifecycles")
    if selected.empty:
        raise ValueError("HYPE baseline has no selected lifecycles")
    return selected


def _verify_source_inputs(args: argparse.Namespace, report: dict[str, object]) -> None:
    source = _object(report.get("source_evidence"), "source evidence")
    pairs = (
        ("development_bars", args.development_bars),
        ("development_funding", args.development_funding),
    )
    for key, path in pairs:
        expected = _object(source.get(key), key)
        if file_evidence(path) != {k: expected[k] for k in ("bytes", "sha256")}:
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
    if file_evidence(data_path) != {k: expected[k] for k in ("bytes", "sha256")}:
        raise ValueError(f"HYPE {key} evidence changed")


def _provenance(
    args: argparse.Namespace,
    baseline: dict[str, object],
    split: dict[str, object],
    generator: dict[str, dict[str, object]],
) -> dict[str, object]:
    paths = (
        args.baseline / "manifest.json",
        args.baseline / "report.json",
        args.baseline / "development_trades.parquet",
        args.baseline / "confirmation_trades.parquet",
        args.development_bars,
        args.development_funding,
        args.confirmation_candles,
        args.confirmation_funding,
    )
    return {
        "baseline_mode": baseline.get("mode"),
        "frozen_entry_policy_id": _POLICY_ID,
        "development_split": split,
        "source_evidence": {str(path.resolve()): file_evidence(path) for path in paths},
        "generator_identity": generator,
    }


def _generator_identity() -> dict[str, dict[str, object]]:
    paths = (
        Path(__file__),
        _ROOT / "src/hypervector/research/hype_mature_profit_floor_sensitivity.py",
        _ROOT / "src/hypervector/cohort_profit_lock_policy.py",
        _ROOT / "src/hypervector/research/hype_breakout_exit_market.py",
        _ROOT / "src/hypervector/research/hype_breakout_exit_experiment.py",
        _ROOT / "src/hypervector/research/hype_breakout_exit_models.py",
    )
    return {str(path.resolve()): file_evidence(path) for path in paths}


def _require_unchanged(expected: dict[str, dict[str, object]]) -> None:
    observed = {path: file_evidence(Path(path)) for path in expected}
    if observed != expected:
        raise RuntimeError("HYPE mature-floor generator changed during evaluation")


def _json_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"required HYPE evidence does not exist: {path}")
    return _object(json.loads(path.read_text(encoding="utf-8")), str(path))


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} evidence must be an object")
    return value


def main() -> None:
    """Publish one immutable authority-free sensitivity report."""
    args = build_parser().parse_args()
    report = run(args)
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.out),
                "disposition": report["disposition"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
