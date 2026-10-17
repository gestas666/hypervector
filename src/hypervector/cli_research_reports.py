"""Read-only summary commands for the durable research database."""

from __future__ import annotations

import argparse

import duckdb

from hypervector.cli_research_support import (
    print_failure,
    print_success,
    research_database_path,
)
from hypervector.data.research_database import ResearchDatabase
from hypervector.data.cohort_research_database import cohort_live_freshness


def cmd_research_db_status(args: argparse.Namespace) -> int:
    """Report current DuckDB research-market table counts."""
    path = research_database_path(args)
    if not path.is_file():
        return print_failure(
            FileNotFoundError(f"research database is missing: {path}"), args
        )
    try:
        database = ResearchDatabase(path)
        report: dict[str, object] = {
            "ok": True,
            "database_path": str(path.resolve()),
            "summary": database.summary(),
            "live_events": database.live_event_summary(),
            "cohort_live": database.cohort_live_summary(),
            "cohort_live_freshness": cohort_live_freshness(path),
            "portfolio_research": database.portfolio_research_summary(),
        }
    except (duckdb.Error, OSError, ValueError) as exc:
        return print_failure(exc, args)
    return print_success(report)


def cmd_research_db_shadow_trades(args: argparse.Namespace) -> int:
    """Report causally attributed completed shadow trades."""
    path = research_database_path(args)
    if not path.is_file():
        return print_failure(
            FileNotFoundError(f"research database is missing: {path}"), args
        )
    try:
        report = {
            "ok": True,
            "database_path": str(path.resolve()),
            **ResearchDatabase(path).shadow_trade_attribution_summary(),
            "venue": "hyperliquid",
        }
    except (duckdb.Error, OSError, ValueError) as exc:
        return print_failure(exc, args)
    return print_success(report)
