#!/usr/bin/env python3
"""Publish post-hoc attribution for the rejected V58 BTC pullback route."""

from __future__ import annotations

import argparse
from dataclasses import asdict
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
from hypervector.research.btc_trend_pullback_failure_attribution import (
    BtcTrendPullbackFailureObservation,
    attribute_btc_trend_pullback_failures,
    build_btc_trend_pullback_failure_report,
)
from hypervector.research.btc_trend_pullback_reacceleration import (
    build_btc_trend_pullback_signals,
)
from hypervector.research.liquidity_sweep_long import load_minute_bars


_DIAGNOSTIC_ID = "V58_BTC_TREND_PULLBACK_FAILURE_ATTRIBUTION_V1"
_CONTRACT_SCHEMA = "v58_btc_trend_pullback_failure_attribution_contract_v1"
_EXPECTED_PARTITIONS = frozenset(("development", "validation", "pseudo_holdout"))
_EXPECTED_ROWS = 147
_IMPLEMENTATION_FILES = (
    "scripts/v58_btc_trend_pullback_failure_attribution.py",
    "src/hypervector/research/btc_trend_pullback_failure_attribution.py",
    "src/hypervector/research/btc_trend_pullback_reacceleration.py",
    "src/hypervector/research/liquidity_sweep_long.py",
)


def build_parser() -> argparse.ArgumentParser:
    """Return the fixed-input authority-none attribution parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bars", type=Path, default=Path("data/cache/BTC_1m_365d.parquet")
    )
    parser.add_argument(
        "--trades",
        type=Path,
        default=Path(
            "data/logs/research/bidirectional_cohort/"
            "v58_btc_trend_pullback_reacceleration_20260821_v1/trades.parquet"
        ),
    )
    parser.add_argument(
        "--rejected-result",
        type=Path,
        default=Path(
            "docs/research-journal/"
            "v58-btc-trend-pullback-reacceleration-result-20260821-v1.json"
        ),
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path(
            "docs/research-journal/"
            "v58-btc-trend-pullback-failure-attribution-contract-20260821-v1.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/logs/research/bidirectional_cohort/"
            "v58_btc_trend_pullback_failure_attribution_20260821_v1"
        ),
    )
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Build and publish one immutable source-bound attribution bundle."""
    if args.output.exists():
        raise FileExistsError(f"BTC failure attribution output exists: {args.output}")
    project_root = Path(__file__).resolve().parents[1]
    sources = _source_evidence(args, project_root)
    implementation = _implementation_identity(project_root)
    bars = load_minute_bars(args.bars)
    diagnostics = build_btc_trend_pullback_signals(bars).diagnostics_15m
    trades = pd.read_parquet(args.trades)
    observations = attribute_btc_trend_pullback_failures(bars, diagnostics, trades)
    _require_scope(observations)
    report = {
        **build_btc_trend_pullback_failure_report(observations),
        "diagnostic_id": _DIAGNOSTIC_ID,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "observation_rows": len(observations),
        "source_evidence": sources,
        "implementation_identity": implementation,
    }
    _require_unchanged(args, project_root, sources, implementation)
    _publish_bundle(args.output, report, observations)
    return args.output


def main() -> int:
    """Publish the immutable report-only bundle and print its path."""
    output = run_command(build_parser().parse_args())
    print(output.resolve())
    return 0


def _source_evidence(
    args: argparse.Namespace, project_root: Path
) -> dict[str, dict[str, object]]:
    contract_path = args.contract.resolve()
    if not contract_path.is_file():
        raise FileNotFoundError(
            f"BTC failure attribution contract missing: {contract_path}"
        )
    contract = _load_json(contract_path)
    _validate_contract(contract)
    registered = _mapping(contract.get("source_evidence"), "source evidence")
    sources = {
        "bars": args.bars,
        "trades": args.trades,
        "rejected_result": args.rejected_result,
    }
    output = {"contract": {"path": str(contract_path), **file_evidence(contract_path)}}
    for name, path in sources.items():
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(
                f"BTC failure attribution {name} missing: {resolved}"
            )
        observed = {"path": str(resolved), **file_evidence(resolved)}
        _validate_registered_source(project_root, name, observed, registered)
        output[name] = observed
    return output


def _validate_contract(contract: dict[str, object]) -> None:
    if contract.get("schema_version") != _CONTRACT_SCHEMA:
        raise ValueError("BTC failure attribution contract schema drifted")
    if contract.get("diagnostic_id") != _DIAGNOSTIC_ID:
        raise ValueError("BTC failure attribution diagnostic identity drifted")
    authority = _mapping(contract.get("authority"), "contract authority")
    if authority.get("execution_authority") != "none" or not authority.get(
        "report_only"
    ):
        raise ValueError("BTC failure attribution contract acquired authority")


def _validate_registered_source(
    project_root: Path,
    name: str,
    observed: dict[str, object],
    registered: dict[str, object],
) -> None:
    expected = _mapping(registered.get(name), f"registered {name}")
    expected_path = (project_root / str(expected.get("path"))).resolve()
    if expected_path != Path(str(observed["path"])):
        raise ValueError(f"BTC failure attribution {name} path drifted")
    if any(expected.get(key) != observed.get(key) for key in ("bytes", "sha256")):
        raise ValueError(f"BTC failure attribution {name} bytes drifted")


def _implementation_identity(project_root: Path) -> dict[str, object]:
    files: dict[str, dict[str, object]] = {}
    digest = hashlib.sha256()
    for relative in _IMPLEMENTATION_FILES:
        path = project_root / relative
        if not path.is_file():
            raise FileNotFoundError(f"BTC failure attribution source missing: {path}")
        evidence = file_evidence(path)
        files[relative] = evidence
        digest.update(f"{relative}:{evidence['sha256']}\n".encode())
    return {"aggregate_sha256": digest.hexdigest(), "files": files}


def _require_scope(
    observations: tuple[BtcTrendPullbackFailureObservation, ...],
) -> None:
    if len(observations) != _EXPECTED_ROWS:
        raise ValueError("BTC failure attribution expected exactly 147 trades")
    partitions = {row.partition for row in observations}
    outcomes = {row.outcome for row in observations}
    if partitions != _EXPECTED_PARTITIONS or outcomes != {"stop", "target"}:
        raise ValueError("BTC failure attribution scope drifted")


def _require_unchanged(
    args: argparse.Namespace,
    project_root: Path,
    sources: dict[str, dict[str, object]],
    implementation: dict[str, object],
) -> None:
    if _source_evidence(args, project_root) != sources:
        raise RuntimeError("BTC failure attribution source changed during evaluation")
    if _implementation_identity(project_root) != implementation:
        raise RuntimeError(
            "BTC failure attribution implementation changed during evaluation"
        )


def _publish_bundle(
    output: Path,
    report: dict[str, object],
    observations: tuple[BtcTrendPullbackFailureObservation, ...],
) -> None:
    def writer(staging: Path) -> None:
        report_path = staging / "report.json"
        observations_path = staging / "observations.parquet"
        write_json(report_path, report)
        write_immutable_parquet(
            observations_path, pd.DataFrame(asdict(row) for row in observations)
        )
        manifest = {
            "schema_version": "immutable_evidence_manifest_v1",
            "files": {
                "report.json": file_evidence(report_path),
                "observations.parquet": file_evidence(observations_path),
            },
        }
        write_json(staging / "manifest.json", manifest)

    publish_immutable_directory(output, writer)


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"BTC failure attribution JSON is not an object: {path}")
    return payload


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"BTC failure attribution {label} is invalid")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
