"""CLI workflow for immutable portfolio research decision revisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from hypervector.cli_research_support import (
    print_failure,
    print_success,
    research_database_path,
)
from hypervector.data.research_database import ResearchDatabase


def add_research_journal_parsers(
    subparsers: argparse._SubParsersAction,
) -> None:
    """Register report-only portfolio research journal commands."""
    append = subparsers.add_parser(
        "research-db-journal-append",
        help="Append one source-backed portfolio research decision revision",
    )
    append.add_argument("--record", type=Path, required=True)
    append.add_argument("--database", type=Path)
    append.set_defaults(func=cmd_research_db_journal_append)

    report = subparsers.add_parser(
        "research-db-journal-report",
        help="Report portfolio research revisions and evidence integrity",
    )
    report.add_argument("--hypothesis-id", required=True)
    report.add_argument("--database", type=Path)
    report.set_defaults(func=cmd_research_db_journal_report)


def cmd_research_db_journal_append(args: argparse.Namespace) -> int:
    """Append one immutable source-backed research decision revision."""
    path = research_database_path(args)
    try:
        result = ResearchDatabase(path).append_portfolio_research_revision(
            Path(args.record)
        )
        report: dict[str, object] = {
            "ok": True,
            "report_only": True,
            "execution_authority": "none",
            "database_path": str(path.resolve()),
            "append": result.to_dict(),
        }
    except (duckdb.Error, json.JSONDecodeError, OSError, ValueError) as exc:
        return print_failure(exc)
    return print_success(report)


def cmd_research_db_journal_report(args: argparse.Namespace) -> int:
    """Report one hypothesis history with current evidence-integrity status."""
    path = research_database_path(args)
    if not path.is_file():
        return print_failure(FileNotFoundError(f"research database is missing: {path}"))
    try:
        history = ResearchDatabase(path).portfolio_research_history(
            str(args.hypothesis_id)
        )
        report: dict[str, object] = {
            "ok": True,
            "report_only": True,
            "execution_authority": "none",
            "database_path": str(path.resolve()),
            "history": history,
        }
    except (duckdb.Error, OSError, ValueError) as exc:
        return print_failure(exc)
    return print_success(report)
