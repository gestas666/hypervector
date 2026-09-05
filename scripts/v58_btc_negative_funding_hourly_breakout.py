#!/usr/bin/env python3
"""Publish the preregistered BTC negative-funding hourly-breakout replay."""

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
from hypervector.research.btc_negative_funding_breakout_historical import (
    BtcNegativeFundingBreakoutPartition,
    frozen_btc_negative_funding_breakout_partitions,
    run_btc_negative_funding_breakout_historical,
)
from hypervector.research.liquidity_sweep_long import load_minute_bars
from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)


_YEAR_ID = "20250728T000000000000Z_20260728T000000000000Z"
_HYPOTHESIS = "V58_BTC_NEGATIVE_FUNDING_HOURLY_BREAKOUT_LONG_V1"
_SCHEMA = "v58_btc_negative_funding_hourly_breakout_preregistration_v1"
_GENERATORS = (
    "scripts/v58_btc_negative_funding_hourly_breakout.py",
    "src/hypervector/research/btc_completed_bar_inputs.py",
    "src/hypervector/research/btc_fixed_60_60_replay.py",
    "src/hypervector/research/btc_negative_funding_hourly_breakout.py",
    "src/hypervector/research/btc_negative_funding_breakout_replay.py",
    "src/hypervector/research/btc_negative_funding_breakout_experiment.py",
    "src/hypervector/research/btc_negative_funding_breakout_historical.py",
    "src/hypervector/research/shared_bar_portfolio.py",
    "src/hypervector/research/shared_portfolio_models.py",
)


def build_parser() -> argparse.ArgumentParser:
    """Return the fixed-identity report-only parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bars",
        type=Path,
        default=Path("data/cache/BTC_1m_365d.parquet"),
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
            "v58-btc-negative-funding-hourly-breakout-preregistration-"
            "20260821-v1.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/logs/research/bidirectional_cohort/"
            "v58_btc_negative_funding_hourly_breakout_20260821_v1"
        ),
    )
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Evaluate once and atomically publish a source-bound bundle."""
    if args.output.exists():
        raise FileExistsError(
            f"BTC negative-funding output already exists: {args.output}"
        )
    project_root = Path(__file__).resolve().parents[1]
    sources = _source_evidence(args)
    generators = _generator_identity(project_root)
    partitions = frozen_btc_negative_funding_breakout_partitions()
    market, funding = _load_inputs(args.bars, args.funding, partitions)
    result = run_btc_negative_funding_breakout_historical(
        market,
        funding,
        partitions,
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
            raise FileNotFoundError(
                f"BTC negative-funding {name} is missing: {resolved}"
            )
        evidence[name] = {"path": str(resolved), **file_evidence(resolved)}
    _validate_preregistration(args.preregistration, evidence)
    return evidence


def _validate_preregistration(
    path: Path,
    evidence: dict[str, dict[str, object]],
) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != _SCHEMA:
        raise ValueError("BTC negative-funding preregistration schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("BTC negative-funding preregistration identity drifted")
    authority = payload.get("authority")
    if (
        not isinstance(authority, dict)
        or authority.get("execution_authority") != "none"
    ):
        raise ValueError("BTC negative-funding preregistration acquired authority")
    registered = payload.get("source_evidence")
    if not isinstance(registered, dict):
        raise ValueError("BTC negative-funding preregistration lacks source evidence")
    for name in ("bars", "funding"):
        expected = registered.get(name)
        observed = evidence[name]
        if not isinstance(expected, dict):
            raise ValueError(f"BTC negative-funding preregistration lacks {name}")
        if any(expected.get(key) != observed.get(key) for key in ("bytes", "sha256")):
            raise ValueError(f"BTC negative-funding registered {name} bytes changed")


def _generator_identity(project_root: Path) -> dict[str, object]:
    files: dict[str, dict[str, object]] = {}
    digest = hashlib.sha256()
    for relative in _GENERATORS:
        source = project_root / relative
        if not source.is_file():
            raise FileNotFoundError(f"BTC negative-funding generator missing: {source}")
        evidence = file_evidence(source)
        files[relative] = evidence
        digest.update(f"{relative}:{evidence['sha256']}\n".encode())
    return {"aggregate_sha256": digest.hexdigest(), "files": files}


def _load_inputs(
    bars_path: Path,
    funding_path: Path,
    partitions: tuple[BtcNegativeFundingBreakoutPartition, ...],
) -> tuple[pd.DataFrame, pd.Series]:
    bars = load_minute_bars(bars_path)
    funding = load_verified_hourly_funding(
        [funding_path],
        partitions[0].start_utc,
        partitions[-1].end_utc,
    )
    return attach_hourly_funding(bars, funding), funding


def _require_unchanged(
    args: argparse.Namespace,
    project_root: Path,
    sources: dict[str, dict[str, object]],
    generators: dict[str, object],
) -> None:
    if _source_evidence(args) != sources:
        raise RuntimeError("BTC negative-funding source changed during evaluation")
    if _generator_identity(project_root) != generators:
        raise RuntimeError("BTC negative-funding generator changed during evaluation")


def _partition_record(
    partition: BtcNegativeFundingBreakoutPartition,
) -> dict[str, str]:
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
