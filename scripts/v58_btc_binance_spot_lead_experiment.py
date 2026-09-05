#!/usr/bin/env python3
"""Publish the preregistered BTC Binance-spot-lead catch-up replay."""

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
from hypervector.research.btc_spot_lead_catchup_historical import (
    BtcSpotLeadCatchupPartition,
    frozen_btc_spot_lead_catchup_partitions,
    run_btc_spot_lead_catchup_historical,
)
from hypervector.research.liquidity_sweep_long import load_minute_bars
from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)


_HYPOTHESIS = "V58_BTC_BINANCE_SPOT_LEAD_HL_PERP_CATCHUP_LONG_V1"
_REGISTRATION_SCHEMA = "v58_btc_binance_spot_lead_input_registration_v1"
_REGISTRATION_STATUS = "inputs_hash_bound_before_candidate_signal_or_return_results"
_SOURCE_NAMES = (
    "hyperliquid_btc_1m_bars",
    "hyperliquid_btc_hourly_funding",
    "binance_spot_vendor_manifest",
    "binance_spot_normalized_manifest",
    "binance_spot_normalized_bars",
)
_GENERATORS = (
    "scripts/v58_btc_binance_spot_lead_experiment.py",
    "src/hypervector/research/binance_spot_archive_acquisition.py",
    "src/hypervector/research/binance_spot_archive_normalization.py",
    "src/hypervector/research/btc_completed_bar_inputs.py",
    "src/hypervector/research/btc_fixed_60_60_replay.py",
    "src/hypervector/research/btc_spot_lead_catchup.py",
    "src/hypervector/research/btc_spot_lead_catchup_replay.py",
    "src/hypervector/research/btc_spot_lead_catchup_experiment.py",
    "src/hypervector/research/btc_spot_lead_catchup_historical.py",
    "src/hypervector/research/shared_bar_portfolio.py",
    "src/hypervector/research/shared_portfolio_models.py",
)


def build_parser() -> argparse.ArgumentParser:
    """Return the fixed-identity report-only experiment parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-registration",
        type=Path,
        default=Path(
            "docs/research-journal/"
            "v58-btc-binance-spot-lead-input-registration-20260821-v1.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/logs/research/bidirectional_cohort/"
            "v58_btc_binance_spot_lead_catchup_20260821_v1"
        ),
    )
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Evaluate once and atomically publish a source-bound result bundle."""
    if args.output.exists():
        raise FileExistsError(f"BTC spot-lead output already exists: {args.output}")
    project_root = Path(__file__).resolve().parents[1]
    sources = _registered_sources(args.input_registration)
    generators = _generator_identity(project_root)
    partitions = frozen_btc_spot_lead_catchup_partitions()
    perpetual, spot = _load_inputs(sources, partitions)
    result = run_btc_spot_lead_catchup_historical(perpetual, spot, partitions)
    _require_unchanged(args.input_registration, project_root, sources, generators)
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


def _registered_sources(path: Path) -> dict[str, dict[str, object]]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(
            f"BTC spot-lead input registration is missing: {resolved}"
        )
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    _validate_registration(payload)
    sources = payload["source_evidence"]
    if not isinstance(sources, dict):
        raise ValueError("BTC spot-lead registration lacks source evidence")
    output = {
        name: _verified_registered_file(sources.get(name), name)
        for name in _SOURCE_NAMES
    }
    output["preregistration"] = _verified_registered_file(
        payload.get("preregistration"), "preregistration"
    )
    output["input_registration"] = {
        "path": str(resolved),
        **file_evidence(resolved),
    }
    return output


def _validate_registration(payload: object) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != (
        _REGISTRATION_SCHEMA
    ):
        raise ValueError("BTC spot-lead input registration schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("BTC spot-lead input registration identity drifted")
    if payload.get("status") != _REGISTRATION_STATUS:
        raise ValueError("BTC spot-lead input registration status drifted")
    authority = payload.get("authority")
    if (
        not isinstance(authority, dict)
        or authority.get("execution_authority") != "none"
    ):
        raise ValueError("BTC spot-lead input registration acquired authority")
    scope = payload.get("change_scope")
    if not isinstance(scope, dict) or any(
        scope.get(key) is not False
        for key in (
            "candidate_signal_count_inspected",
            "candidate_returns_inspected",
            "candidate_pnl_inspected",
        )
    ):
        raise ValueError("BTC spot-lead input registration is not outcome-blind")


def _verified_registered_file(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not isinstance(value.get("path"), str):
        raise ValueError(f"BTC spot-lead registration lacks {name}")
    path = Path(value["path"]).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"BTC spot-lead registered {name} is missing: {path}")
    observed = {"path": str(path), **file_evidence(path)}
    if any(value.get(key) != observed.get(key) for key in ("bytes", "sha256")):
        raise ValueError(f"BTC spot-lead registered {name} bytes changed")
    return observed


def _load_inputs(
    sources: dict[str, dict[str, object]],
    partitions: tuple[BtcSpotLeadCatchupPartition, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    bars_path = Path(str(sources["hyperliquid_btc_1m_bars"]["path"]))
    funding_path = Path(str(sources["hyperliquid_btc_hourly_funding"]["path"]))
    spot_path = Path(str(sources["binance_spot_normalized_bars"]["path"]))
    perpetual = load_minute_bars(bars_path)
    funding = load_verified_hourly_funding(
        [funding_path],
        partitions[0].start_utc,
        partitions[-1].end_utc,
    )
    spot = _load_spot_bars(spot_path)
    return attach_hourly_funding(perpetual, funding), spot


def _load_spot_bars(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"BTC spot-lead normalized source lacks columns: {missing}")
    timestamp = pd.to_datetime(frame.pop("timestamp"), utc=True, errors="raise")
    frame.index = pd.DatetimeIndex(timestamp, name="timestamp")
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError(
            "BTC spot-lead normalized timestamps must be unique and increasing"
        )
    if "gap_before_bars" not in frame:
        frame["gap_before_bars"] = 0
    return frame


def _generator_identity(project_root: Path) -> dict[str, object]:
    files: dict[str, dict[str, object]] = {}
    digest = hashlib.sha256()
    for relative in _GENERATORS:
        source = project_root / relative
        if not source.is_file():
            raise FileNotFoundError(f"BTC spot-lead generator missing: {source}")
        evidence = file_evidence(source)
        files[relative] = evidence
        digest.update(f"{relative}:{evidence['sha256']}\n".encode())
    return {"aggregate_sha256": digest.hexdigest(), "files": files}


def _require_unchanged(
    registration: Path,
    project_root: Path,
    sources: dict[str, dict[str, object]],
    generators: dict[str, object],
) -> None:
    if _registered_sources(registration) != sources:
        raise RuntimeError("BTC spot-lead source changed during evaluation")
    if _generator_identity(project_root) != generators:
        raise RuntimeError("BTC spot-lead generator changed during evaluation")


def _partition_record(partition: BtcSpotLeadCatchupPartition) -> dict[str, str]:
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
