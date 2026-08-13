#!/usr/bin/env python3
"""Publish development and later-window HYPE compression-breakout evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    verify_file_evidence,
    write_json,
)
from hypervector.research.hype_breakout_exit_experiment import split_hype_exit_market
from hypervector.research.hype_breakout_exit_market import (
    HypeExitMarketEvidence,
    build_hype_exit_market,
)
from hypervector.research.hype_breakout_exit_models import HypeExitReplayConfig
from hypervector.research.hype_compression_breakout_challenger import (
    build_hype_compression_breakout_bundle,
    build_hype_compression_confirmation,
)
from hypervector.research.hype_compression_exit_challenger import (
    build_hype_compression_exit_study,
)

_ROOT = Path(__file__).resolve().parents[1]
_DEVELOPMENT_BARS = _ROOT / "data/cache/HYPE_1m_365d.parquet"
_DEVELOPMENT_FUNDING = _ROOT / (
    "data/cache/vendor/hyperliquid/HYPE/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)
_CONFIRMATION_DIRECTORY = _ROOT / (
    "data/cache/vendor/0xarchive/hyperliquid/HYPE/"
    "20260728T000000000000Z_20260810T234500000000Z_candles_1m"
)
_CONFIRMATION_FUNDING_DIRECTORY = _ROOT / (
    "data/cache/vendor/hyperliquid/HYPE/"
    "20260728T000000000000Z_20260811T000000000000Z_funding"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable immutable research command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-bars", type=Path, default=_DEVELOPMENT_BARS)
    parser.add_argument(
        "--development-funding",
        type=Path,
        default=_DEVELOPMENT_FUNDING,
    )
    parser.add_argument(
        "--confirmation-directory",
        type=Path,
        default=_CONFIRMATION_DIRECTORY,
    )
    parser.add_argument(
        "--confirmation-funding-directory",
        type=Path,
        default=_CONFIRMATION_FUNDING_DIRECTORY,
    )
    parser.add_argument("--holdout-days", type=int, default=60)
    parser.add_argument("--fold-count", type=int, default=5)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser


def build_replay_config() -> HypeExitReplayConfig:
    """Return the exact v35 HYPE 8h-to-24h execution contract."""
    return HypeExitReplayConfig(
        stop_bps=80.0,
        maximum_hold_minutes=480,
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_minutes=1_440,
    )


def continuous_candle_segments(
    raw_bars: pd.DataFrame,
) -> tuple[tuple[pd.DataFrame, ...], list[dict[str, object]]]:
    """Split ordered one-minute candles at every explicit missing interval."""
    if "timestamp" not in raw_bars:
        raise ValueError("HYPE confirmation candles require timestamp")
    timestamps = pd.to_datetime(raw_bars["timestamp"], utc=True)
    if timestamps.duplicated().any() or not timestamps.is_monotonic_increasing:
        raise ValueError("HYPE confirmation timestamps must be ordered and unique")
    groups = timestamps.diff().ne(pd.Timedelta(minutes=1)).cumsum()
    segments = tuple(part.copy() for _, part in raw_bars.groupby(groups, sort=False))
    gaps = _candle_gaps(timestamps)
    return segments, gaps


def run(args: argparse.Namespace) -> dict[str, object]:
    """Run development selection, then compare its frozen identity later."""
    sources = _source_inputs(args)
    generator = _generator_identity()
    config = build_replay_config()
    development, development_evidence, split = _development_market(
        args,
        config,
    )
    development_bundle = build_hype_compression_breakout_bundle(
        development,
        config=config,
        fold_count=args.fold_count,
    )
    confirmation_markets, gaps, confirmation_evidence = _confirmation_markets(args)
    frozen = str(development_bundle.report["selection"]["selected_challenger"])
    confirmation_bundle = build_hype_compression_confirmation(
        confirmation_markets,
        frozen_policy_id=frozen,
        config=config,
    )
    exit_bundle = build_hype_compression_exit_study(
        development,
        confirmation_markets,
        frozen_compression_policy_id=frozen,
        config=config,
        fold_count=args.fold_count,
    )
    report = _report(
        development_bundle.report,
        confirmation_bundle.report,
        split,
        asdict(development_evidence),
        confirmation_evidence,
        gaps,
        exit_bundle.report,
        sources,
        generator,
    )
    _publish(
        args.out_dir,
        report,
        development_bundle.trade_rows,
        confirmation_bundle.trade_rows,
        exit_bundle.development_trades,
        exit_bundle.confirmation_trades,
        generator,
    )
    return report


def _development_market(
    args: argparse.Namespace,
    config: HypeExitReplayConfig,
) -> tuple[pd.DataFrame, HypeExitMarketEvidence, dict[str, object]]:
    market, evidence = build_hype_exit_market(
        pd.read_parquet(args.development_bars),
        pd.read_parquet(args.development_funding),
    )
    development, _sealed, split = split_hype_exit_market(
        market,
        config,
        args.holdout_days,
    )
    return development, evidence, split


def _confirmation_markets(
    args: argparse.Namespace,
) -> tuple[tuple[pd.DataFrame, ...], list[dict[str, object]], list[dict[str, object]]]:
    raw = pd.read_parquet(args.confirmation_directory / "candles.parquet")
    funding = pd.read_parquet(args.confirmation_funding_directory / "funding.parquet")
    raw_segments, gaps = continuous_candle_segments(raw)
    markets: list[pd.DataFrame] = []
    evidence: list[dict[str, object]] = []
    for segment_number, segment in enumerate(raw_segments, start=1):
        market, segment_evidence = build_hype_exit_market(segment, funding)
        markets.append(market)
        evidence.append({"segment": segment_number, **asdict(segment_evidence)})
    return tuple(markets), gaps, evidence


def _source_inputs(args: argparse.Namespace) -> dict[str, object]:
    _require_file(args.development_bars, "development bars")
    _require_file(args.development_funding, "development funding")
    candle_manifest = _verified_manifest(args.confirmation_directory, "candles")
    funding_manifest = _verified_manifest(
        args.confirmation_funding_directory,
        "funding",
    )
    return {
        "development_bars": _file_reference(args.development_bars),
        "development_funding": _file_reference(args.development_funding),
        "confirmation_candle_manifest": candle_manifest,
        "confirmation_funding_manifest": funding_manifest,
    }


def _verified_manifest(directory: Path, label: str) -> dict[str, object]:
    path = directory / "manifest.json"
    _require_file(path, f"confirmation {label} manifest")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("complete") is not True or payload.get("symbol") != "HYPE":
        raise ValueError(f"HYPE confirmation {label} manifest is incomplete or wrong")
    verify_file_evidence(directory, payload.get("files"))
    return {"path": str(path.resolve()), **file_evidence(path), "payload": payload}


def _report(
    development: dict[str, object],
    confirmation: dict[str, object],
    split: dict[str, object],
    development_evidence: dict[str, object],
    confirmation_evidence: list[dict[str, object]],
    gaps: list[dict[str, object]],
    exit_study: dict[str, object],
    sources: dict[str, object],
    generator: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "hype_compression_breakout_challenger_report_only",
        "execution_authority": "none",
        "development_split": split,
        "development_market": development_evidence,
        "development": development,
        "later_confirmation_market": confirmation_evidence,
        "later_confirmation_gaps": gaps,
        "later_confirmation": confirmation,
        "compression_exit_challenger": exit_study,
        "source_evidence": sources,
        "generator_identity": generator,
    }


def _publish(
    output: Path,
    report: dict[str, object],
    development_trades: pd.DataFrame,
    confirmation_trades: pd.DataFrame,
    exit_development_trades: pd.DataFrame,
    exit_confirmation_trades: pd.DataFrame,
    generator: dict[str, dict[str, object]],
) -> None:
    def write_bundle(staging: Path) -> None:
        development_path = staging / "development_trades.parquet"
        confirmation_path = staging / "confirmation_trades.parquet"
        exit_development_path = staging / "exit_development_trades.parquet"
        exit_confirmation_path = staging / "exit_confirmation_trades.parquet"
        report_path = staging / "report.json"
        development_trades.to_parquet(development_path, index=False)
        confirmation_trades.to_parquet(confirmation_path, index=False)
        exit_development_trades.to_parquet(exit_development_path, index=False)
        exit_confirmation_trades.to_parquet(exit_confirmation_path, index=False)
        report["sidecars"] = {
            "development_trades": _file_reference(development_path),
            "confirmation_trades": _file_reference(confirmation_path),
            "exit_development_trades": _file_reference(exit_development_path),
            "exit_confirmation_trades": _file_reference(exit_confirmation_path),
        }
        write_json(report_path, report)
        if _generator_identity() != generator:
            raise RuntimeError("HYPE challenger generator changed during publication")
        write_json(
            staging / "manifest.json",
            {
                "schema_version": 1,
                "complete": True,
                "files": {
                    path.name: file_evidence(path)
                    for path in (
                        report_path,
                        development_path,
                        confirmation_path,
                        exit_development_path,
                        exit_confirmation_path,
                    )
                },
            },
        )

    publish_immutable_directory(output, write_bundle)


def _candle_gaps(timestamps: pd.Series) -> list[dict[str, object]]:
    gaps: list[dict[str, object]] = []
    for previous, current in zip(timestamps.iloc[:-1], timestamps.iloc[1:]):
        missing = int((current - previous) / pd.Timedelta(minutes=1)) - 1
        if missing > 0:
            gaps.append(
                {
                    "missing_start_utc": (
                        previous + pd.Timedelta(minutes=1)
                    ).isoformat(),
                    "missing_end_utc": (current - pd.Timedelta(minutes=1)).isoformat(),
                    "missing_minutes": missing,
                }
            )
    return gaps


def _generator_identity() -> dict[str, dict[str, object]]:
    paths = sorted((_ROOT / "src/hypervector").rglob("*.py")) + [Path(__file__)]
    return {str(path.relative_to(_ROOT)): file_evidence(path) for path in paths}


def _file_reference(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"HYPE {label} does not exist: {path}")


def main() -> None:
    """Run the report-only command and print its immutable location."""
    args = build_parser().parse_args()
    report = run(args)
    print(
        json.dumps(
            {
                "ok": True,
                "out_dir": str(args.out_dir.resolve()),
                "execution_authority": report["execution_authority"],
                "frozen_policy_id": report["later_confirmation"]["frozen_policy_id"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
