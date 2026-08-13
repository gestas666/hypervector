"""DuckDB extraction tests for one-minute order-flow impulse inputs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb

from hypervector.research.orderflow_impulse_data import (
    audit_orderflow_coverage,
    load_orderflow_impulse_inputs,
)


def _database(path: Path) -> None:
    connection = duckdb.connect(str(path))
    connection.execute(
        """
        CREATE TABLE canonical_trade_1m_bars (
            symbol VARCHAR, bar_open_at TIMESTAMPTZ, open DOUBLE,
            high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE,
            trade_count BIGINT
        );
        CREATE TABLE replay_public_trades (
            symbol VARCHAR, ts_utc TIMESTAMPTZ, aggressor_side VARCHAR,
            size DOUBLE
        );
        CREATE TABLE replay_book_snapshots (
            symbol VARCHAR, ts_exchange_ms BIGINT, ts_utc TIMESTAMPTZ,
            imbalance_5 DOUBLE, mid_price DOUBLE, micro_price DOUBLE,
            spread_bps DOUBLE, bid_depth_10 DOUBLE, ask_depth_10 DOUBLE
        );
        """
    )
    for minute in range(8):
        stamp = f"2026-01-01 00:0{minute}:00+00"
        connection.execute(
            "INSERT INTO canonical_trade_1m_bars VALUES "
            "('BTC', ?, 100, 101, 99, 100.5, 10, 2)",
            [stamp],
        )
        connection.execute(
            "INSERT INTO replay_public_trades VALUES "
            "('BTC', ?::TIMESTAMPTZ + INTERVAL 10 SECOND, 'buy', 7), "
            "('BTC', ?::TIMESTAMPTZ + INTERVAL 20 SECOND, 'sell', 3)",
            [stamp, stamp],
        )
        connection.execute(
            "INSERT INTO replay_book_snapshots VALUES "
            "('BTC', ?, ?::TIMESTAMPTZ + INTERVAL 10 SECOND, 0.1, 100, "
            "100.01, 1, 12, 8), "
            "('BTC', ?, ?::TIMESTAMPTZ + INTERVAL 50 SECOND, 0.3, 100, "
            "100.02, 2, 14, 6)",
            [minute * 2 + 1, stamp, minute * 2 + 2, stamp],
        )
    connection.close()


def test_loader_builds_causal_one_minute_trade_and_book_rows(tmp_path: Path) -> None:
    """The loader must aggregate only observations inside each completed minute."""
    database = tmp_path / "market.duckdb"
    _database(database)

    inputs = load_orderflow_impulse_inputs(
        database,
        "BTC",
        datetime(2026, 1, 1, 0, 2, tzinfo=UTC),
        datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
        warmup_minutes=2,
        horizon_minutes=2,
    )

    assert len(inputs.bars) == 7
    assert inputs.trades.iloc[0]["buy_volume"] == 7.0
    assert inputs.trades.iloc[0]["sell_volume"] == 3.0
    assert inputs.books.iloc[0]["imbalance_5_last"] == 0.3
    assert abs(inputs.books.iloc[0]["imbalance_5_delta"] - 0.2) < 1e-12
    assert inputs.books.iloc[0]["last_book_at"].second == 50


def test_coverage_audit_reports_missing_assets_without_fabrication(
    tmp_path: Path,
) -> None:
    """Missing ETH/HYPE history must remain an explicit zero-row result."""
    database = tmp_path / "market.duckdb"
    _database(database)

    report = audit_orderflow_coverage(database, ("BTC", "ETH"))
    by_symbol = report.set_index("symbol")

    assert by_symbol.loc["BTC", "book_rows"] == 16
    assert by_symbol.loc["ETH", "book_rows"] == 0
    assert by_symbol.loc["ETH", "trade_rows"] == 0
