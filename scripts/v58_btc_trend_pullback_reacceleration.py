#!/usr/bin/env python3
"""Publish the preregistered BTC trend-pullback causal replay."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    write_immutable_parquet,
    write_json,
)
from hypervector.research.btc_trend_pullback_historical import (
    BtcTrendPullbackPartition,
    frozen_btc_trend_pullback_partitions,
    run_btc_trend_pullback_historical,
)
from hypervector.research.btc_v58_hulk_route_source import (
    BtcHulkRouteSource,
    build_v58_hulk_short_events,
)
from hypervector.research.backtest_lab_cipher_adapter import (
    inspect_backtest_lab_sources,
)
from hypervector.research.liquidity_sweep_long import load_minute_bars
from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)


_YEAR_ID = "20250728T000000000000Z_20260728T000000000000Z"
_HYPOTHESIS = "V58_BTC_15M_TREND_PULLBACK_REACCELERATION_LONG_V1"
_SCHEMA = "v58_btc_trend_pullback_reacceleration_preregistration_v1"
_GENERATORS = (
    "scripts/v58_btc_trend_pullback_reacceleration.py",
    "src/hypervector/research/btc_trend_pullback_reacceleration.py",
    "src/hypervector/research/btc_trend_pullback_reacceleration_replay.py",
    "src/hypervector/research/btc_trend_pullback_experiment.py",
    "src/hypervector/research/btc_trend_pullback_historical.py",
    "src/hypervector/research/btc_trend_pullback_route_competition.py",
    "src/hypervector/research/btc_v58_hulk_route_source.py",
    "src/hypervector/research/btc_sweep_primary_relaxation.py",
    "src/hypervector/research/btc_sweep_primary_relaxation_replay.py",
    "src/hypervector/research/liquidity_sweep_long.py",
    "src/hypervector/research/backtest_lab_cipher_adapter.py",
    "src/hypervector/research/hulk_smash_candidates.py",
    "src/hypervector/research/hulk_smash_quality.py",
    "src/hypervector/research/hulk_smash_rebuilt_signals.py",
    "src/hypervector/research/market_cipher_strategy_research.py",
    "src/hypervector/research/shared_bar_portfolio.py",
    "src/hypervector/research/shared_portfolio_models.py",
)


def build_parser() -> argparse.ArgumentParser:
    """Return the fixed-identity report-only parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backtest-lab-root",
        type=Path,
        default=Path("../backtest-lab/backtest_lab"),
    )
    parser.add_argument(
        "--bars", type=Path, default=Path("data/cache/BTC_1m_365d.parquet")
    )
    parser.add_argument(
        "--funding",
        type=Path,
        default=Path(
            f"data/cache/vendor/hyperliquid/BTC/{_YEAR_ID}_funding/funding.parquet"
        ),
    )
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path(
            "docs/research-journal/"
            "v58-btc-trend-pullback-reacceleration-preregistration-20260821-v1.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/logs/research/bidirectional_cohort/"
            "v58_btc_trend_pullback_reacceleration_20260821_v1"
        ),
    )
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Evaluate once and atomically publish a source-bound bundle."""
    if args.output.exists():
        raise FileExistsError(f"BTC pullback output already exists: {args.output}")
    project_root = Path(__file__).resolve().parents[1]
    sources = _source_evidence(args)
    generators = _generator_identity(project_root, args.backtest_lab_root)
    partitions = frozen_btc_trend_pullback_partitions()
    market = _load_market(args.bars, args.funding, partitions)
    robust, tuned = _hulk_sources(market, args.backtest_lab_root)
    hulk_identity = {
        "robust": robust.source_identity,
        "tuned": tuned.source_identity,
    }
    result = run_btc_trend_pullback_historical(
        market,
        partitions,
        hulk_events=(*robust.events, *tuned.events),
        hulk_source_identity=hulk_identity,
    )
    _require_unchanged(args, project_root, sources, generators)
    report = {
        **result.report,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "hypothesis_id": _HYPOTHESIS,
        "partition_bounds": [_partition_record(value) for value in partitions],
        "input_evidence": sources,
        "generator_identity": generators,
        "trade_sidecar_rows": len(result.trade_rows),
    }
    _publish_bundle(args.output, report, result.trade_rows)
    return args.output


def main() -> int:
    """Publish immutable authority-none evidence and print its path."""
    output = run_command(build_parser().parse_args())
    print(output.resolve())
    return 0


def _source_evidence(args: argparse.Namespace) -> dict[str, dict[str, object]]:
    paths = {
        "bars": args.bars,
        "funding": args.funding,
        "preregistration": args.preregistration,
    }
    evidence: dict[str, dict[str, object]] = {}
    for name, source in paths.items():
        resolved = source.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"BTC pullback {name} is missing: {resolved}")
        evidence[name] = {"path": str(resolved), **file_evidence(resolved)}
    _validate_preregistration(args.preregistration, evidence)
    return evidence


def _validate_preregistration(
    path: Path, evidence: dict[str, dict[str, object]]
) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != _SCHEMA:
        raise ValueError("BTC pullback preregistration schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("BTC pullback preregistration identity drifted")
    authority = payload.get("authority")
    if (
        not isinstance(authority, dict)
        or authority.get("execution_authority") != "none"
    ):
        raise ValueError("BTC pullback preregistration acquired execution authority")
    registered = payload.get("source_evidence")
    if not isinstance(registered, dict):
        raise ValueError("BTC pullback preregistration lacks source evidence")
    for name in ("bars", "funding"):
        expected = registered.get(name)
        observed = evidence[name]
        if not isinstance(expected, dict):
            raise ValueError(f"BTC pullback preregistration lacks {name}")
        if any(expected.get(key) != observed.get(key) for key in ("bytes", "sha256")):
            raise ValueError(f"BTC pullback registered {name} bytes changed")


def _generator_identity(
    project_root: Path, backtest_lab_root: Path
) -> dict[str, object]:
    files: dict[str, dict[str, object]] = {}
    digest = hashlib.sha256()
    for relative in _GENERATORS:
        source = project_root / relative
        if not source.is_file():
            raise FileNotFoundError(f"BTC pullback generator is missing: {source}")
        evidence = file_evidence(source)
        files[relative] = evidence
        digest.update(f"{relative}:{evidence['sha256']}\n".encode())
    external = inspect_backtest_lab_sources(backtest_lab_root)
    digest.update(json.dumps(external, sort_keys=True).encode())
    return {
        "aggregate_sha256": digest.hexdigest(),
        "files": files,
        "backtest_lab": external,
    }


def _load_market(
    bars_path: Path,
    funding_path: Path,
    partitions: tuple[BtcTrendPullbackPartition, ...],
) -> pd.DataFrame:
    bars = load_minute_bars(bars_path)
    funding = load_verified_hourly_funding(
        [funding_path], partitions[0].start_utc, partitions[-1].end_utc
    )
    return attach_hourly_funding(bars, funding)


def _require_unchanged(
    args: argparse.Namespace,
    project_root: Path,
    sources: dict[str, dict[str, object]],
    generators: dict[str, object],
) -> None:
    if _source_evidence(args) != sources:
        raise RuntimeError("BTC pullback source changed during evaluation")
    if _generator_identity(project_root, args.backtest_lab_root) != generators:
        raise RuntimeError("BTC pullback generator changed during evaluation")


def _hulk_sources(
    market: pd.DataFrame, backtest_lab_root: Path
) -> tuple[BtcHulkRouteSource, BtcHulkRouteSource]:
    robust = build_v58_hulk_short_events(
        market, backtest_lab_root, "hulk_expansion_short_robust_v3"
    )
    tuned = build_v58_hulk_short_events(
        market, backtest_lab_root, "hulk_expansion_short_tuned_v2"
    )
    return robust, tuned


def _partition_record(partition: BtcTrendPullbackPartition) -> dict[str, str]:
    return {
        "name": partition.name,
        "start_utc": partition.start_utc.isoformat(),
        "end_utc": partition.end_utc.isoformat(),
    }


def _publish_bundle(
    output: Path,
    report: dict[str, object],
    trade_rows: tuple[dict[str, object], ...],
) -> None:
    def writer(staging: Path) -> None:
        report_path = staging / "report.json"
        trades_path = staging / "trades.parquet"
        write_json(report_path, report)
        write_immutable_parquet(trades_path, pd.DataFrame(trade_rows))
        manifest = {
            "schema_version": "immutable_evidence_manifest_v1",
            "files": {
                "report.json": file_evidence(report_path),
                "trades.parquet": file_evidence(trades_path),
            },
        }
        write_json(staging / "manifest.json", manifest)

    publish_immutable_directory(output, writer)


if __name__ == "__main__":
    raise SystemExit(main())
