"""Operational resource-policy tests for report-only DuckDB access."""

from __future__ import annotations

from pathlib import Path

from hypervector.data.reporting_duckdb import (
    REPORTING_MEMORY_LIMIT,
    REPORTING_THREADS,
    connect_reporting_database,
)


def test_reporting_connection_enforces_bounded_resources(tmp_path: Path) -> None:
    """Always-on reporting must not inherit DuckDB's machine-wide defaults."""
    assert REPORTING_MEMORY_LIMIT == "4GB"
    assert REPORTING_THREADS == 2

    with connect_reporting_database(tmp_path / "report.duckdb") as connection:
        memory, threads = connection.execute(
            "SELECT current_setting('memory_limit'), current_setting('threads')"
        ).fetchone()

    assert memory == "3.7 GiB"
    assert threads == 2
