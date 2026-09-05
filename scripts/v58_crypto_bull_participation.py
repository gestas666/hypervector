#!/usr/bin/env python3
"""Publish the frozen V58 four-crypto bull-participation replay."""

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
from hypervector.research.crypto_bull_participation_historical import (
    load_crypto_bull_historical_inputs,
    run_crypto_bull_participation_historical,
)

_HYPOTHESIS = "V58_CRYPTO_BULL_BREADTH_PARTICIPATION_LONG_V1"
_SCHEMA = "v58_crypto_bull_breadth_participation_preregistration_v1"
_AMENDMENT_SCHEMA = "v58_crypto_bull_breadth_participation_source_amendment_v1"
_FUNDING_WINDOW = "20250728T000000000000Z_20260728T000000000000Z_funding"
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_GENERATOR_FILES = (
    "scripts/v58_crypto_bull_participation.py",
    "src/hypervector/research/crypto_bull_participation_models.py",
    "src/hypervector/research/crypto_bull_participation_signals.py",
    "src/hypervector/research/crypto_bull_participation_replay.py",
    "src/hypervector/research/crypto_bull_participation_experiment.py",
    "src/hypervector/research/crypto_bull_participation_historical.py",
)


def build_parser() -> argparse.ArgumentParser:
    """Return the fixed report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path(
            "docs/research-journal/"
            "v58-crypto-bull-breadth-participation-preregistration-20260822-v1.json"
        ),
    )
    parser.add_argument(
        "--source-amendment",
        type=Path,
        default=Path(
            "docs/research-journal/"
            "v58-crypto-bull-breadth-participation-source-amendment-20260822-v1.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/logs/research/bidirectional_cohort/"
            "v58_crypto_bull_participation_20260822_v1"
        ),
    )
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Evaluate once and atomically publish a source-bound result bundle."""
    if args.output.exists():
        raise FileExistsError(f"immutable replay output already exists: {args.output}")
    project_root = args.project_root.resolve()
    sources = _source_evidence(
        project_root, args.preregistration, args.source_amendment
    )
    generator = _generator_identity(project_root)
    inputs = load_crypto_bull_historical_inputs(project_root)
    result = run_crypto_bull_participation_historical(inputs)
    _require_unchanged(
        project_root,
        args.preregistration,
        args.source_amendment,
        sources,
        generator,
    )
    report = {
        **result.report,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "hypothesis_id": _HYPOTHESIS,
        "input_evidence": sources,
        "market_source_identity": inputs.source_identity,
        "generator_identity": generator,
        "trade_sidecar_rows": len(result.trade_rows),
    }
    _publish_bundle(args.output, report, result.trade_rows)
    return args.output


def main() -> int:
    """Run the immutable authority-none replay and print its resolved path."""
    output = run_command(build_parser().parse_args())
    print(output.resolve())
    return 0


def _source_evidence(
    project_root: Path, preregistration: Path, source_amendment: Path
) -> dict[str, dict[str, object]]:
    prereg = preregistration.resolve()
    amendment = source_amendment.resolve()
    paths = {"preregistration": prereg, "source_amendment": amendment}
    for symbol in _SYMBOLS:
        paths[f"{symbol}_minutes"] = (
            project_root / "data" / "cache" / f"{symbol}_1m_365d.parquet"
        )
        paths[f"{symbol}_funding"] = (
            project_root
            / "data"
            / "cache"
            / "vendor"
            / "hyperliquid"
            / symbol
            / _FUNDING_WINDOW
            / "funding.parquet"
        )
    _validate_preregistration(prereg)
    _validate_source_amendment(amendment)
    output: dict[str, dict[str, object]] = {}
    for name, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(
                f"crypto bull-participation source is missing: {path}"
            )
        output[name] = {"path": str(path), **file_evidence(path)}
    return output


def _validate_preregistration(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("crypto bull-participation preregistration must be an object")
    if payload.get("schema_version") != _SCHEMA:
        raise ValueError("crypto bull-participation preregistration schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("crypto bull-participation hypothesis identity drifted")


def _validate_source_amendment(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("crypto bull source amendment must be an object")
    if payload.get("schema_version") != _AMENDMENT_SCHEMA:
        raise ValueError("crypto bull source amendment schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("crypto bull source amendment identity drifted")
    trigger = payload.get("trigger")
    if (
        not isinstance(trigger, dict)
        or trigger.get("performance_results_seen") is not False
    ):
        raise ValueError("crypto bull source amendment lacks outcome-blind status")


def _generator_identity(project_root: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    files: dict[str, dict[str, object]] = {}
    for relative in _GENERATOR_FILES:
        path = project_root / relative
        if not path.is_file():
            raise FileNotFoundError(f"crypto bull generator is missing: {path}")
        evidence = file_evidence(path)
        files[relative] = evidence
        digest.update(f"{relative}:{evidence['sha256']}\n".encode())
    return {"aggregate_sha256": digest.hexdigest(), "files": files}


def _require_unchanged(
    project_root: Path,
    preregistration: Path,
    source_amendment: Path,
    sources: dict[str, dict[str, object]],
    generator: dict[str, object],
) -> None:
    if _source_evidence(project_root, preregistration, source_amendment) != sources:
        raise RuntimeError("crypto bull-participation source changed during replay")
    if _generator_identity(project_root) != generator:
        raise RuntimeError("crypto bull-participation generator changed during replay")


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
