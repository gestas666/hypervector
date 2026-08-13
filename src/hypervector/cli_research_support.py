"""Shared output and path helpers for research database commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from hypervector.infra import paths_for


def research_database_path(args: argparse.Namespace) -> Path:
    """Resolve an explicit database or the configured research-store default."""
    if args.database is not None:
        return Path(args.database)
    return paths_for(args.data_root).research_db


def print_failure(exc: Exception) -> int:
    """Print one machine-readable command failure."""
    print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
    return 1


def print_success(report: dict[str, object]) -> int:
    """Print one machine-readable successful research result."""
    print(json.dumps(report, indent=2))
    return 0
