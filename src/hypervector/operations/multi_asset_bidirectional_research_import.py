#!/usr/bin/env python3
"""Incrementally import private live cohort journals into report-only DuckDB."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from pathlib import Path
import sys

import duckdb

from hypervector.data.research_database import ResearchDatabase
from hypervector.research.cohort_live_portfolio_archive import (
    CohortAccountingEpoch,
    CohortLiveArchiveSource,
    CohortLiveFillIdentity,
    PORTFOLIO_ARCHIVE_PROJECTION_REVISION,
    load_cohort_live_archive_source,
    load_cohort_live_portfolio_archive,
)

_DEFAULT_LEDGER_ROOT = Path("data/live/bidirectional_cohort")
_DEFAULT_DATABASE = Path("data/research/market.duckdb")


def build_parser() -> argparse.ArgumentParser:
    """Declare explicit source and destination paths for the installed service."""
    parser = argparse.ArgumentParser(
        description="Import append-only live cohort journals without execution authority."
    )
    parser.add_argument("--ledger-root", type=Path, default=_DEFAULT_LEDGER_ROOT)
    parser.add_argument("--database", type=Path, default=_DEFAULT_DATABASE)
    parser.add_argument("--cached-checkpoint", type=Path)
    parser.add_argument("--accounting-epoch-id")
    parser.add_argument("--accounting-epoch-profile-fingerprint")
    parser.add_argument("--accounting-epoch-start-ms", type=int)
    parser.add_argument(
        "--accounting-epoch-included-profile-fingerprint",
        action="append",
        default=[],
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse explicit source and destination paths."""
    return build_parser().parse_args(argv)


def build_import_report(
    database_path: Path,
    ledger_root: Path,
    *,
    cached_checkpoint_path: Path | None = None,
    accounting_epoch: CohortAccountingEpoch | None = None,
) -> dict[str, object]:
    """Import journals and rebuild projections only after execution fills change."""
    database = ResearchDatabase(database_path)
    ingest = database.ingest_cohort_live_ledger(ledger_root)
    source = load_cohort_live_archive_source(database_path)
    identity = source.identity
    archive = _cached_archive(cached_checkpoint_path, identity, accounting_epoch)
    archive_status = "reused_by_fill_identity"
    if archive is None:
        archive = _build_archive(database_path, source, accounting_epoch)
        archive_status = (
            "rebuilt_full_manual"
            if cached_checkpoint_path is None
            else "rebuilt_after_fill_identity_change"
        )
    report: dict[str, object] = {
        "ok": True,
        "report_only": True,
        "execution_authority": "none",
        "database_path": str(database_path.resolve()),
        "ledger_root": str(ledger_root.resolve()),
        "ingest": ingest.to_dict(),
        "fill_identity": identity.to_dict(),
        "archive_status": archive_status,
        "portfolio_archive": archive,
    }
    if cached_checkpoint_path is None:
        report["summary"] = database.cohort_live_summary()
    return report


def _build_archive(
    database_path: Path,
    source: CohortLiveArchiveSource,
    accounting_epoch: CohortAccountingEpoch | None,
) -> dict[str, object]:
    if accounting_epoch is None:
        return load_cohort_live_portfolio_archive(database_path, source=source)
    return load_cohort_live_portfolio_archive(
        database_path,
        source=source,
        accounting_epoch=accounting_epoch,
    )


def _cached_archive(
    checkpoint_path: Path | None,
    identity: CohortLiveFillIdentity,
    accounting_epoch: CohortAccountingEpoch | None = None,
) -> dict[str, object] | None:
    if checkpoint_path is None or not checkpoint_path.is_file():
        return None
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if not isinstance(checkpoint, Mapping):
        raise ValueError("cached checkpoint must be a JSON object")
    contract = checkpoint.get("checkpoint_contract")
    if not isinstance(contract, Mapping):
        raise ValueError("cached checkpoint omitted its report-only contract")
    if contract.get("report_only") is not True:
        raise ValueError("cached checkpoint is not report-only")
    if contract.get("execution_authority") != "none":
        raise ValueError("cached checkpoint unexpectedly has execution authority")
    audit = checkpoint.get("audit")
    if not isinstance(audit, Mapping):
        raise ValueError("cached checkpoint omitted its audit projection")
    archive = audit.get("portfolio_archive")
    if not isinstance(archive, Mapping):
        return None
    if archive.get("schema_version") != 1:
        raise ValueError("cached portfolio archive schema is unsupported")
    if archive.get("mode") != "cohort_live_portfolio_archive_v1":
        raise ValueError("cached portfolio archive mode is unsupported")
    if archive.get("projection_revision") != PORTFOLIO_ARCHIVE_PROJECTION_REVISION:
        return None
    if archive.get("source_execution") != identity.to_dict():
        return None
    expected_epoch = None if accounting_epoch is None else accounting_epoch.to_dict()
    if archive.get("accounting_epoch") != expected_epoch:
        return None
    return dict(archive)


def _accounting_epoch(args: argparse.Namespace) -> CohortAccountingEpoch | None:
    values = (
        args.accounting_epoch_id,
        args.accounting_epoch_profile_fingerprint,
        args.accounting_epoch_start_ms,
    )
    included = tuple(args.accounting_epoch_included_profile_fingerprint)
    if all(value is None for value in values) and not included:
        return None
    if any(value is None for value in values):
        raise ValueError("accounting epoch requires id, profile fingerprint, and start")
    return CohortAccountingEpoch(
        str(values[0]),
        str(values[1]),
        int(values[2]),
        included_profile_fingerprints=included,
    )


def main(argv: list[str] | None = None) -> int:
    """Run one atomic incremental import and print a JSON report."""
    args = parse_args(argv)
    try:
        report = build_import_report(
            args.database,
            args.ledger_root,
            cached_checkpoint_path=args.cached_checkpoint,
            accounting_epoch=_accounting_epoch(args),
        )
    except (duckdb.Error, json.JSONDecodeError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
