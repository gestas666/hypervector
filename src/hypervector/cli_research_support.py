"""Shared output and path helpers for research database commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hypervector.infra import paths_for


def research_database_path(args: argparse.Namespace) -> Path:
    """Resolve an explicit database or the configured research-store default."""
    if args.database is not None:
        return Path(args.database)
    return paths_for(args.data_root).research_db


def print_failure(exc: Exception, args: argparse.Namespace | None = None) -> int:
    """Print one machine-readable command failure (the shared error shape)."""
    from hypervector.commands.common import print_error

    return print_error(args, exc)


def print_success(report: dict[str, object]) -> int:
    """Print one machine-readable successful research result."""
    print(json.dumps(report, indent=2))
    return 0
