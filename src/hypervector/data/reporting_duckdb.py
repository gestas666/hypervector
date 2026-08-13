"""Bounded DuckDB connection policy for always-on reporting workloads."""

from __future__ import annotations

from pathlib import Path

import duckdb

REPORTING_MEMORY_LIMIT = "4GB"
REPORTING_THREADS = 2


def connect_reporting_database(
    path: Path,
    *,
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    """Open a reporting connection with explicit memory and thread limits."""
    return duckdb.connect(
        str(path),
        read_only=read_only,
        config={
            "memory_limit": REPORTING_MEMORY_LIMIT,
            "threads": str(REPORTING_THREADS),
        },
    )
