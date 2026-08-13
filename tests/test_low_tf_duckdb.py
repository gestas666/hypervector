"""Determinism tests for low-timeframe DuckDB extraction."""

from __future__ import annotations

from hypervector.research.low_tf_duckdb import (
    _BARS_SQL,
    _TRADES_SQL,
    _configure_connection,
)


class _RecordingConnection:
    """Minimal connection double recording deterministic session settings."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str) -> _RecordingConnection:
        """Record one DuckDB configuration statement."""
        self.statements.append(statement)
        return self


def test_low_tf_loader_pins_timezone_and_suppresses_progress() -> None:
    """Research extraction must use the declared timezone without noisy output."""
    connection = _RecordingConnection()

    _configure_connection(connection)

    assert connection.statements == [
        "SET TimeZone='UTC'",
        "SET enable_progress_bar=false",
    ]


def test_low_tf_queries_use_exact_sums_and_ordered_trade_identity() -> None:
    """Parallel query scheduling must not change price or volume evidence."""
    assert "first(price ORDER BY ts_exchange_ms, trade_id)" in _BARS_SQL
    assert "last(price ORDER BY ts_exchange_ms, trade_id)" in _BARS_SQL
    assert "sum(CAST(size AS DECIMAL(38, 18)))" in _BARS_SQL
    assert _TRADES_SQL.count("sum(CAST(size AS DECIMAL(38, 18)))") == 4
