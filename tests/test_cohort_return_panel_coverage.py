"""Tests for exact-roster return-panel coverage evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from hypervector.research.cohort_return_panel_coverage import (
    build_return_panel_coverage_report,
)


def _connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE canonical_trade_5m_bars (
            symbol VARCHAR NOT NULL,
            bar_open_at TIMESTAMPTZ NOT NULL,
            open DOUBLE NOT NULL,
            high DOUBLE NOT NULL,
            low DOUBLE NOT NULL,
            close DOUBLE NOT NULL,
            volume DOUBLE NOT NULL,
            trade_count BIGINT NOT NULL
        )
        """
    )
    return connection


def _insert(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
    timestamp: datetime,
) -> None:
    connection.execute(
        "INSERT INTO canonical_trade_5m_bars VALUES (?, ?, 1, 1, 1, 1, 1, 1)",
        [symbol, timestamp],
    )


def test_missing_roster_assets_withhold_covariance_weighting() -> None:
    connection = _connection()
    timestamp = datetime(2026, 8, 1, tzinfo=UTC)
    _insert(connection, "BTC", timestamp)
    _insert(connection, "ETH", timestamp)

    report = build_return_panel_coverage_report(
        connection,
        ("BTC", "ETH", "xyz:SP500"),
    )

    assert report["status"] == "insufficient_synchronized_coverage"
    assert report["missing_symbols"] == ["xyz:SP500"]
    assert report["common_timestamp_count"] == 0
    assert report["covariance_weighting_status"] == "withheld"
    assert report["contract"]["execution_authority"] == "none"


def test_complete_roster_reports_only_exact_shared_timestamps() -> None:
    connection = _connection()
    start = datetime(2026, 8, 1, tzinfo=UTC)
    for offset in range(3):
        _insert(connection, "BTC", start + timedelta(minutes=5 * offset))
    for offset in (0, 2):
        _insert(connection, "ETH", start + timedelta(minutes=5 * offset))

    report = build_return_panel_coverage_report(connection, ("BTC", "ETH"))

    assert report["status"] == "synchronized_panel_constructible"
    assert report["missing_symbols"] == []
    assert report["common_timestamp_count"] == 2
    assert report["common_start_utc"] == start.isoformat()
    assert report["common_end_utc"] == (start + timedelta(minutes=10)).isoformat()
    assert report["by_symbol"]["BTC"]["bar_count"] == 3
    assert report["by_symbol"]["ETH"]["bar_count"] == 2
    assert report["covariance_weighting_status"] == "coverage_only_not_qualified"


def test_duplicate_symbol_timestamp_fails_closed() -> None:
    connection = _connection()
    timestamp = datetime(2026, 8, 1, tzinfo=UTC)
    _insert(connection, "BTC", timestamp)
    _insert(connection, "BTC", timestamp)

    with pytest.raises(ValueError, match="duplicate symbol/timestamp"):
        build_return_panel_coverage_report(connection, ("BTC",))


def test_missing_required_table_fails_fast() -> None:
    connection = duckdb.connect(":memory:")

    with pytest.raises(ValueError, match="missing required table"):
        build_return_panel_coverage_report(connection, ("BTC",))
