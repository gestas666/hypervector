#!/usr/bin/env python3
"""Publish the preregistered BTC DVOL-VRP continuation-long replay."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    verify_file_evidence,
    write_immutable_parquet,
    write_json,
)
from hypervector.research.btc_dvol_vrp_historical import (
    BtcDvolVrpPartition,
    frozen_btc_dvol_vrp_partitions,
    run_btc_dvol_vrp_historical,
)
from hypervector.research.liquidity_sweep_long import load_minute_bars
from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)


_HYPOTHESIS = "V58_BTC_DVOL_VRP_CONTINUATION_LONG_V1"
_PREREGISTRATION_SCHEMA = "v58_btc_dvol_vrp_continuation_long_preregistration_v1"
_PREREGISTRATION_STATUS = "preregistered_before_source_acquisition_or_outcomes"
_REGISTRATION_SCHEMA = "v58_btc_dvol_vrp_continuation_long_input_registration_v1"
_REGISTRATION_STATUS = "inputs_hash_bound_before_candidate_signal_or_return_results"
_DERIBIT_SCHEMA = "deribit_btc_dvol_hourly_bundle_v1"
_SOURCE_NAMES = (
    "deribit_dvol_manifest",
    "deribit_dvol_parquet",
    "hyperliquid_btc_1m_bars",
    "hyperliquid_btc_hourly_funding",
)
_GENERATORS = (
    "scripts/v58_btc_dvol_vrp_experiment.py",
    "src/hypervector/data/oxa_storage.py",
    "src/hypervector/research/deribit_dvol_acquisition.py",
    "src/hypervector/research/btc_dvol_vrp_features.py",
    "src/hypervector/research/btc_dvol_vrp_continuation.py",
    "src/hypervector/research/btc_dvol_vrp_replay.py",
    "src/hypervector/research/btc_dvol_vrp_experiment.py",
    "src/hypervector/research/btc_dvol_vrp_historical.py",
    "src/hypervector/research/btc_fixed_60_60_replay.py",
    "src/hypervector/research/btc_sweep_primary_relaxation.py",
    "src/hypervector/research/shared_bar_portfolio.py",
    "src/hypervector/research/shared_portfolio_inputs.py",
    "src/hypervector/research/shared_portfolio_models.py",
)


def build_parser() -> argparse.ArgumentParser:
    """Return the immutable authority-none experiment parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-registration",
        type=Path,
        default=Path(
            "docs/research-journal/"
            "v58-btc-dvol-vrp-continuation-long-"
            "input-registration-20260821-v1.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/logs/research/bidirectional_cohort/"
            "v58_btc_dvol_vrp_continuation_long_20260821_v1"
        ),
    )
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Run once and atomically publish a source-bound result bundle."""
    if args.output.exists():
        raise FileExistsError(f"BTC DVOL-VRP output already exists: {args.output}")
    project_root = Path(__file__).resolve().parents[1]
    sources, generators = _registered_sources(args.input_registration, project_root)
    partitions = frozen_btc_dvol_vrp_partitions()
    market, dvol = _load_inputs(sources, partitions)
    result = run_btc_dvol_vrp_historical(market, dvol, partitions)
    _require_unchanged(args.input_registration, project_root, sources, generators)
    report = {
        **result.report,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "hypothesis_id": _HYPOTHESIS,
        "partition_bounds": [_partition_record(value) for value in partitions],
        "input_evidence": sources,
        "generator_identity": generators,
        "trade_sidecar_rows": len(result.trade_rows),
        "live_promotion_authorized": False,
    }
    _publish_bundle(args.output, report, result.trade_rows)
    return args.output


def main() -> int:
    """Publish immutable report-only evidence and print its path."""
    output = run_command(build_parser().parse_args())
    print(output.resolve())
    return 0


def _registered_sources(
    path: Path,
    project_root: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(
            f"BTC DVOL-VRP input registration is missing: {resolved}"
        )
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    generators = _validate_registration(payload, project_root)
    evidence = payload.get("source_evidence")
    if not isinstance(evidence, dict):
        raise ValueError("BTC DVOL-VRP registration lacks source evidence")
    sources = {
        name: _verified_registered_file(evidence.get(name), name)
        for name in _SOURCE_NAMES
    }
    preregistration = _verified_registered_file(
        payload.get("preregistration"), "preregistration"
    )
    _validate_preregistration(Path(str(preregistration["path"])))
    sources["preregistration"] = preregistration
    sources["input_registration"] = {"path": str(resolved), **file_evidence(resolved)}
    return sources, generators


def _validate_registration(payload: object, project_root: Path) -> dict[str, object]:
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != _REGISTRATION_SCHEMA
    ):
        raise ValueError("BTC DVOL-VRP input registration schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("BTC DVOL-VRP input registration identity drifted")
    if payload.get("status") != _REGISTRATION_STATUS:
        raise ValueError("BTC DVOL-VRP input registration status drifted")
    authority = payload.get("authority")
    if (
        not isinstance(authority, dict)
        or authority.get("execution_authority") != "none"
    ):
        raise ValueError("BTC DVOL-VRP input registration acquired authority")
    if authority.get("report_only") is not True:
        raise ValueError("BTC DVOL-VRP input registration is not report-only")
    _validate_outcome_blind_scope(payload.get("change_scope"))
    current = _generator_identity(project_root)
    if payload.get("generator_identity") != current:
        raise ValueError("BTC DVOL-VRP registered generator identity drifted")
    return current


def _validate_outcome_blind_scope(value: object) -> None:
    fields = (
        "candidate_signal_count_inspected",
        "candidate_returns_inspected",
        "candidate_pnl_inspected",
    )
    if not isinstance(value, dict) or any(
        value.get(key) is not False for key in fields
    ):
        raise ValueError("BTC DVOL-VRP input registration is not outcome-blind")


def _validate_preregistration(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != _PREREGISTRATION_SCHEMA
    ):
        raise ValueError("BTC DVOL-VRP preregistration schema drifted")
    if (
        payload.get("hypothesis_id") != _HYPOTHESIS
        or payload.get("status") != _PREREGISTRATION_STATUS
    ):
        raise ValueError("BTC DVOL-VRP preregistration identity drifted")
    if payload.get("execution_authority") != "none":
        raise ValueError("BTC DVOL-VRP preregistration acquired authority")
    fields = (
        "outcomes_inspected_before_preregistration",
        "candidate_signal_counts_inspected",
        "candidate_forward_returns_inspected",
        "candidate_trade_outcomes_inspected",
    )
    if any(payload.get(key) is not False for key in fields):
        raise ValueError("BTC DVOL-VRP preregistration is not outcome-blind")


def _verified_registered_file(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not isinstance(value.get("path"), str):
        raise ValueError(f"BTC DVOL-VRP registration lacks {name}")
    path = Path(value["path"]).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"BTC DVOL-VRP registered {name} is missing: {path}")
    observed = {"path": str(path), **file_evidence(path)}
    if any(value.get(key) != observed[key] for key in ("bytes", "sha256")):
        raise ValueError(f"BTC DVOL-VRP registered {name} bytes changed")
    return observed


def _load_inputs(
    sources: dict[str, dict[str, object]],
    partitions: tuple[BtcDvolVrpPartition, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dvol = _load_deribit_dvol(sources)
    bars_path = Path(str(sources["hyperliquid_btc_1m_bars"]["path"]))
    funding_path = Path(str(sources["hyperliquid_btc_hourly_funding"]["path"]))
    bars = load_minute_bars(bars_path)
    funding = load_verified_hourly_funding(
        [funding_path], partitions[0].start_utc, partitions[-1].end_utc
    )
    return attach_hourly_funding(bars, funding), dvol


def _load_deribit_dvol(
    sources: dict[str, dict[str, object]],
) -> pd.DataFrame:
    manifest_path = Path(str(sources["deribit_dvol_manifest"]["path"]))
    dvol_path = Path(str(sources["deribit_dvol_parquet"]["path"]))
    if manifest_path.parent != dvol_path.parent:
        raise ValueError("BTC DVOL-VRP Deribit bundle paths do not share one directory")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != _DERIBIT_SCHEMA
    ):
        raise ValueError("BTC DVOL-VRP Deribit manifest schema drifted")
    if manifest.get("execution_authority") != "none":
        raise ValueError("BTC DVOL-VRP Deribit manifest acquired authority")
    if manifest.get("candidate_outcomes_computed") is not False:
        raise ValueError("BTC DVOL-VRP Deribit manifest contains candidate outcomes")
    verify_file_evidence(manifest_path.parent, manifest.get("files"))
    files = manifest.get("files")
    if not isinstance(files, dict) or files.get("dvol.parquet") != file_evidence(
        dvol_path
    ):
        raise ValueError("BTC DVOL-VRP Deribit normalized evidence drifted")
    return pd.read_parquet(dvol_path)


def _generator_identity(project_root: Path) -> dict[str, object]:
    files: dict[str, dict[str, object]] = {}
    digest = hashlib.sha256()
    for relative in _GENERATORS:
        source = project_root / relative
        if not source.is_file():
            raise FileNotFoundError(f"BTC DVOL-VRP generator is missing: {source}")
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
    current_sources, current_generators = _registered_sources(
        registration, project_root
    )
    if current_sources != sources:
        raise RuntimeError("BTC DVOL-VRP source changed during evaluation")
    if current_generators != generators:
        raise RuntimeError("BTC DVOL-VRP generator changed during evaluation")


def _partition_record(partition: BtcDvolVrpPartition) -> dict[str, str]:
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
