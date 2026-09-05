#!/usr/bin/env python3
"""Publish the preregistered BTC IBIT creation-persistence replay."""

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
from hypervector.research.blackrock_ibit_history import (
    IBIT_COMPLETE_SHARES_REQUIRED_FROM,
    parse_blackrock_ibit_history,
)
from hypervector.research.btc_ibit_creation_historical import (
    BtcIbitCreationPartition,
    frozen_btc_ibit_creation_partitions,
    run_btc_ibit_creation_historical,
)
from hypervector.research.liquidity_sweep_long import load_minute_bars
from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)


_HYPOTHESIS = "V58_BTC_IBIT_CREATION_PERSISTENCE_LONG_V1"
_PREREGISTRATION_SCHEMA = "v58_btc_ibit_creation_persistence_long_preregistration_v1"
_PREREGISTRATION_STATUS = (
    "preregistered_before_blackrock_source_acquisition_or_candidate_results"
)
_REGISTRATION_SCHEMA = "v58_btc_ibit_creation_persistence_long_input_registration_v1"
_REGISTRATION_STATUS = "inputs_hash_bound_before_candidate_signal_or_return_results"
_BLACKROCK_SCHEMA = "blackrock_ibit_historical_bundle_v1"
_SOURCE_NAMES = (
    "blackrock_ibit_manifest",
    "blackrock_ibit_raw",
    "blackrock_ibit_history",
    "source_integrity_addendum",
    "hyperliquid_btc_1m_bars",
    "hyperliquid_btc_hourly_funding",
)
_GENERATORS = (
    "scripts/v58_btc_ibit_creation_experiment.py",
    "src/hypervector/data/oxa_storage.py",
    "src/hypervector/research/blackrock_ibit_history.py",
    "src/hypervector/research/blackrock_ibit_acquisition.py",
    "src/hypervector/research/btc_fixed_60_60_replay.py",
    "src/hypervector/research/btc_ibit_creation_long.py",
    "src/hypervector/research/btc_ibit_creation_replay.py",
    "src/hypervector/research/btc_ibit_creation_experiment.py",
    "src/hypervector/research/btc_ibit_creation_historical.py",
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
            "v58-btc-ibit-creation-persistence-long-"
            "input-registration-20260821-v1.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/logs/research/bidirectional_cohort/"
            "v58_btc_ibit_creation_persistence_long_20260821_v1"
        ),
    )
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Run once and atomically publish a source-bound result bundle."""
    if args.output.exists():
        raise FileExistsError(
            f"BTC IBIT experiment output already exists: {args.output}"
        )
    project_root = Path(__file__).resolve().parents[1]
    sources, generators = _registered_sources(args.input_registration, project_root)
    partitions = frozen_btc_ibit_creation_partitions()
    market, history = _load_inputs(sources, partitions)
    result = run_btc_ibit_creation_historical(market, history, partitions)
    _require_unchanged(
        args.input_registration,
        project_root,
        sources,
        generators,
    )
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
        raise FileNotFoundError(f"BTC IBIT input registration is missing: {resolved}")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    generators = _validate_registration(payload, project_root)
    evidence = payload.get("source_evidence")
    if not isinstance(evidence, dict):
        raise ValueError("BTC IBIT registration lacks source evidence")
    sources = {
        name: _verified_registered_file(evidence.get(name), name)
        for name in _SOURCE_NAMES
    }
    preregistration = _verified_registered_file(
        payload.get("preregistration"), "preregistration"
    )
    _validate_preregistration(Path(str(preregistration["path"])))
    sources["preregistration"] = preregistration
    sources["input_registration"] = {
        "path": str(resolved),
        **file_evidence(resolved),
    }
    return sources, generators


def _validate_registration(
    payload: object,
    project_root: Path,
) -> dict[str, object]:
    if not isinstance(payload, dict) or payload.get("schema_version") != (
        _REGISTRATION_SCHEMA
    ):
        raise ValueError("BTC IBIT input registration schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("BTC IBIT input registration identity drifted")
    if payload.get("status") != _REGISTRATION_STATUS:
        raise ValueError("BTC IBIT input registration status drifted")
    authority = payload.get("authority")
    if (
        not isinstance(authority, dict)
        or authority.get("execution_authority") != "none"
    ):
        raise ValueError("BTC IBIT input registration acquired authority")
    if authority.get("report_only") is not True:
        raise ValueError("BTC IBIT input registration is not report-only")
    _validate_outcome_blind_scope(payload.get("change_scope"))
    current = _generator_identity(project_root)
    if payload.get("generator_identity") != current:
        raise ValueError("BTC IBIT registered generator identity drifted")
    return current


def _validate_outcome_blind_scope(value: object) -> None:
    if not isinstance(value, dict) or any(
        value.get(key) is not False
        for key in (
            "candidate_signal_count_inspected",
            "candidate_returns_inspected",
            "candidate_pnl_inspected",
        )
    ):
        raise ValueError("BTC IBIT input registration is not outcome-blind")


def _validate_preregistration(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != (
        _PREREGISTRATION_SCHEMA
    ):
        raise ValueError("BTC IBIT preregistration schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("BTC IBIT preregistration identity drifted")
    if payload.get("status") != _PREREGISTRATION_STATUS:
        raise ValueError("BTC IBIT preregistration status drifted")
    authority = payload.get("authority")
    if (
        not isinstance(authority, dict)
        or authority.get("execution_authority") != "none"
    ):
        raise ValueError("BTC IBIT preregistration acquired authority")


def _verified_registered_file(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not isinstance(value.get("path"), str):
        raise ValueError(f"BTC IBIT registration lacks {name}")
    path = Path(value["path"]).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"BTC IBIT registered {name} is missing: {path}")
    observed = {"path": str(path), **file_evidence(path)}
    if any(value.get(key) != observed[key] for key in ("bytes", "sha256")):
        raise ValueError(f"BTC IBIT registered {name} bytes changed")
    return observed


def _load_inputs(
    sources: dict[str, dict[str, object]],
    partitions: tuple[BtcIbitCreationPartition, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    history = _load_blackrock_history(sources)
    bars_path = Path(str(sources["hyperliquid_btc_1m_bars"]["path"]))
    funding_path = Path(str(sources["hyperliquid_btc_hourly_funding"]["path"]))
    bars = load_minute_bars(bars_path)
    funding = load_verified_hourly_funding(
        [funding_path],
        partitions[0].start_utc,
        partitions[-1].end_utc,
    )
    return attach_hourly_funding(bars, funding), history


def _load_blackrock_history(
    sources: dict[str, dict[str, object]],
) -> pd.DataFrame:
    manifest_path = Path(str(sources["blackrock_ibit_manifest"]["path"]))
    raw_path = Path(str(sources["blackrock_ibit_raw"]["path"]))
    history_path = Path(str(sources["blackrock_ibit_history"]["path"]))
    if len({manifest_path.parent, raw_path.parent, history_path.parent}) != 1:
        raise ValueError("BTC IBIT BlackRock bundle paths do not share one directory")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_blackrock_manifest(
        manifest,
        raw_path,
        history_path,
        sources["source_integrity_addendum"],
    )
    parsed = parse_blackrock_ibit_history(
        raw_path.read_bytes(),
        allow_share_placeholders_before=IBIT_COMPLETE_SHARES_REQUIRED_FROM,
    )
    normalized = pd.read_parquet(history_path)
    try:
        pd.testing.assert_frame_equal(parsed, normalized)
    except AssertionError as exc:
        raise ValueError("BTC IBIT normalized history differs from raw source") from exc
    return normalized


def _validate_blackrock_manifest(
    manifest: object,
    raw_path: Path,
    history_path: Path,
    addendum: dict[str, object],
) -> None:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != (
        _BLACKROCK_SCHEMA
    ):
        raise ValueError("BTC IBIT BlackRock manifest schema drifted")
    if manifest.get("execution_authority") != "none":
        raise ValueError("BTC IBIT BlackRock manifest acquired authority")
    if manifest.get("candidate_outcomes_computed") is not False:
        raise ValueError("BTC IBIT BlackRock manifest contains candidate outcomes")
    context = manifest.get("context")
    if not isinstance(context, dict) or context.get("source_integrity_addendum") != (
        addendum
    ):
        raise ValueError("BTC IBIT BlackRock manifest addendum binding drifted")
    files = manifest.get("files")
    expected = {
        "fund_data.xml": file_evidence(raw_path),
        "history.parquet": file_evidence(history_path),
    }
    if files != expected:
        raise ValueError("BTC IBIT BlackRock manifest file evidence drifted")


def _generator_identity(project_root: Path) -> dict[str, object]:
    files: dict[str, dict[str, object]] = {}
    digest = hashlib.sha256()
    for relative in _GENERATORS:
        source = project_root / relative
        if not source.is_file():
            raise FileNotFoundError(f"BTC IBIT generator is missing: {source}")
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
        registration,
        project_root,
    )
    if current_sources != sources:
        raise RuntimeError("BTC IBIT source changed during evaluation")
    if current_generators != generators:
        raise RuntimeError("BTC IBIT generator changed during evaluation")


def _partition_record(partition: BtcIbitCreationPartition) -> dict[str, str]:
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
