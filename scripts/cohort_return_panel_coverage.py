#!/usr/bin/env python3
"""Publish exact-roster synchronized bar coverage for a cohort candidate."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import UTC, datetime
import json
from pathlib import Path

import duckdb

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_return_panel_coverage import (
    build_return_panel_coverage_report,
)
from hypervector.research.mu_hip3_archive_provenance import (
    require_unchanged_generator,
    source_tree_identity,
)


def build_parser() -> argparse.ArgumentParser:
    """Build explicit database, candidate-config, and output arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Audit one exact candidate roster using a read-only DuckDB connection."""
    config = load_multi_asset_live_config(args.config, mode="observe")
    database_evidence = _database_evidence(args.database)
    connection = duckdb.connect(str(args.database), read_only=True)
    try:
        report = build_return_panel_coverage_report(connection, config.symbols)
    finally:
        connection.close()
    _require_database_unchanged(args.database, database_evidence)
    project_root = Path(__file__).resolve().parents[1]
    report.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "candidate_profile": {
                "profile_id": config.profile_id,
                "profile_fingerprint": config.profile_fingerprint,
            },
            "evidence": {
                "database": database_evidence,
                "config": _path_evidence(args.config),
            },
            "generator_identity": source_tree_identity(
                project_root,
                Path(__file__).resolve(),
            ),
        }
    )
    return report


def _database_evidence(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"research database does not exist: {path}")
    stat = path.stat()
    evidence = file_evidence(path)
    return {
        "path": str(path.resolve()),
        "sha256": evidence["sha256"],
        "size_bytes": evidence["bytes"],
        "modified_at_ns": stat.st_mtime_ns,
    }


def _path_evidence(path: Path) -> dict[str, object]:
    evidence = file_evidence(path)
    return {
        "path": str(path.resolve()),
        "sha256": evidence["sha256"],
        "size_bytes": evidence["bytes"],
    }


def _require_database_unchanged(
    path: Path,
    evidence: Mapping[str, object],
) -> None:
    stat = path.stat()
    if stat.st_size != evidence.get("size_bytes") or stat.st_mtime_ns != evidence.get(
        "modified_at_ns"
    ):
        raise RuntimeError("research database changed during coverage audit")


def main() -> int:
    """Publish one source-stable immutable coverage artifact."""
    args = build_parser().parse_args()
    report = run_report(args)
    identity = report.get("generator_identity")
    if not isinstance(identity, Mapping):
        raise ValueError("generator identity is missing")
    require_unchanged_generator(
        dict(identity),
        Path(__file__).resolve().parents[1],
        Path(__file__).resolve(),
    )
    _require_database_unchanged(args.database, report["evidence"]["database"])
    write_immutable_json(args.out, report)
    print(
        json.dumps(
            {
                "output": str(args.out),
                "status": report["status"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
