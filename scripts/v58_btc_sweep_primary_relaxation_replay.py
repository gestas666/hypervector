#!/usr/bin/env python3
"""Publish the preregistered V58 BTC sweep-relaxation causal replay."""

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
from hypervector.research.btc_sweep_primary_relaxation_historical import (
    BtcSweepHistoricalPartition,
    frozen_btc_sweep_historical_partitions,
    run_btc_sweep_primary_relaxation_historical,
)
from hypervector.research.liquidity_sweep_long import load_minute_bars
from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)


_YEAR_ID = "20250728T000000000000Z_20260728T000000000000Z"
_HYPOTHESIS = "V58_BTC_SWEEP_PRIMARY_RELAXATION_CAUSAL_REPLAY_V1"
_GENERATOR_FILES = (
    "scripts/v58_btc_sweep_primary_relaxation_replay.py",
    "src/hypervector/research/btc_sweep_primary_relaxation.py",
    "src/hypervector/research/btc_sweep_primary_relaxation_replay.py",
    "src/hypervector/research/btc_sweep_primary_relaxation_experiment.py",
    "src/hypervector/research/btc_sweep_primary_relaxation_historical.py",
    "src/hypervector/research/shared_bar_portfolio.py",
    "src/hypervector/research/shared_portfolio_models.py",
)


def build_parser() -> argparse.ArgumentParser:
    """Return the fixed-identity report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
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
            "v58-btc-sweep-primary-relaxation-causal-replay-"
            "preregistration-20260821-v1.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/logs/research/bidirectional_cohort/"
            "v58_btc_sweep_primary_relaxation_replay_20260821_v1"
        ),
    )
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Evaluate once and atomically publish a source-bound immutable bundle."""
    if args.output.exists():
        raise FileExistsError(f"0xArchive output already exists: {args.output}")
    project_root = Path(__file__).resolve().parents[1]
    sources = _source_evidence(args.bars, args.funding, args.preregistration)
    generator = _generator_identity(project_root)
    partitions = frozen_btc_sweep_historical_partitions()
    market = _load_market(args.bars, args.funding, partitions)
    result = run_btc_sweep_primary_relaxation_historical(market, partitions)
    _require_unchanged(args, project_root, sources, generator)
    report = {
        **result.report,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "hypothesis_id": _HYPOTHESIS,
        "partition_bounds": [_partition_record(value) for value in partitions],
        "input_evidence": sources,
        "generator_identity": generator,
        "trade_sidecar_rows": len(result.trade_rows),
    }
    _publish_bundle(args.output, report, result.trade_rows)
    return args.output


def main() -> int:
    """Run the immutable report-only command and print its resolved path."""
    output = run_command(build_parser().parse_args())
    print(output.resolve())
    return 0


def _source_evidence(
    bars: Path,
    funding: Path,
    preregistration: Path,
) -> dict[str, dict[str, object]]:
    paths = {"bars": bars, "funding": funding, "preregistration": preregistration}
    evidence: dict[str, dict[str, object]] = {}
    for name, path in paths.items():
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(
                f"BTC sweep-relaxation {name} is missing: {resolved}"
            )
        evidence[name] = {"path": str(resolved), **file_evidence(resolved)}
    _validate_preregistration(preregistration)
    return evidence


def _validate_preregistration(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("BTC sweep-relaxation preregistration must be an object")
    if payload.get("schema_version") != "cohort_strategy_preregistration_v1":
        raise ValueError("BTC sweep-relaxation preregistration schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("BTC sweep-relaxation preregistration identity drifted")


def _generator_identity(project_root: Path) -> dict[str, object]:
    files: dict[str, dict[str, object]] = {}
    digest = hashlib.sha256()
    for relative in _GENERATOR_FILES:
        path = project_root / relative
        if not path.is_file():
            raise FileNotFoundError(
                f"BTC sweep-relaxation generator is missing: {path}"
            )
        evidence = file_evidence(path)
        files[relative] = evidence
        digest.update(f"{relative}:{evidence['sha256']}\n".encode())
    return {"aggregate_sha256": digest.hexdigest(), "files": files}


def _load_market(
    bars_path: Path,
    funding_path: Path,
    partitions: tuple[BtcSweepHistoricalPartition, ...],
) -> pd.DataFrame:
    bars = load_minute_bars(bars_path)
    funding = load_verified_hourly_funding(
        [funding_path],
        partitions[0].start_utc,
        partitions[-1].end_utc,
    )
    return attach_hourly_funding(bars, funding)


def _require_unchanged(
    args: argparse.Namespace,
    project_root: Path,
    sources: dict[str, dict[str, object]],
    generator: dict[str, object],
) -> None:
    observed_sources = _source_evidence(args.bars, args.funding, args.preregistration)
    if observed_sources != sources:
        raise RuntimeError("BTC sweep-relaxation source changed during evaluation")
    if _generator_identity(project_root) != generator:
        raise RuntimeError("BTC sweep-relaxation generator changed during evaluation")


def _partition_record(partition: BtcSweepHistoricalPartition) -> dict[str, str]:
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
