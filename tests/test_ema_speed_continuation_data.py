"""Exact-input tests for the 15-minute EMA-speed challenger."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pytest

from hypervector.research.ema_speed_continuation_data import (
    load_ema_speed_inputs,
)


_START = datetime(2025, 5, 1, tzinfo=timezone.utc)


def test_loader_aggregates_complete_trade_bars_and_exact_l2_quotes(
    tmp_path: Path,
) -> None:
    """Three child bars and fresh L2 produce one executable 15-minute row."""
    database = tmp_path / "market.duckdb"
    _write_fixture(database, missing_child=False)
    inputs = load_ema_speed_inputs(database, "BTC", _START, _START + timedelta(hours=1))
    first = inputs.bars.iloc[0]
    assert first["open"] == 100.0
    assert first["high"] == 103.0
    assert first["low"] == 99.0
    assert first["close"] == 102.5
    assert bool(first["source_complete"])
    assert first["entry_bid"] == 99.9
    assert first["entry_ask"] == pytest.approx(100.1)
    assert first["close_bid"] == pytest.approx(102.4)
    assert first["close_ask"] == pytest.approx(102.6)
    assert first["risk_low"] == pytest.approx(99.9)
    assert first["risk_high"] == pytest.approx(102.6)
    assert first["source_snapshot_count"] == 181
    assert first["first_boundary_delay_ms"] == 1_000
    assert first["end_boundary_age_ms"] == 1_000
    assert bool(first["l2_path_complete"])


def test_loader_materializes_missing_child_as_explicit_gap(tmp_path: Path) -> None:
    """A missing five-minute child cannot be silently collapsed into a bar."""
    database = tmp_path / "market.duckdb"
    _write_fixture(database, missing_child=True)
    inputs = load_ema_speed_inputs(database, "BTC", _START, _START + timedelta(hours=1))
    assert len(inputs.bars) == 4
    assert not bool(inputs.bars.iloc[0]["source_complete"])
    assert inputs.bars.iloc[0]["trade_child_count"] == 2
    assert inputs.bars.index[1] - inputs.bars.index[0] == timedelta(minutes=15)


def test_loader_rejects_unregistered_symbol(tmp_path: Path) -> None:
    """The data seam cannot silently broaden the preregistered universe."""
    database = tmp_path / "market.duckdb"
    _write_fixture(database, missing_child=False)
    with pytest.raises(ValueError, match="BTC or SOL"):
        load_ema_speed_inputs(database, "ETH", _START, _START + timedelta(hours=1))


def _write_fixture(path: Path, *, missing_child: bool) -> None:
    with duckdb.connect(str(path)) as connection:
        _create_tables(connection)
        children = [0, 5, 10]
        if missing_child:
            children.remove(5)
        for offset in children:
            _insert_trade_bar(connection, _START + timedelta(minutes=offset), offset)
        for bar in range(4):
            _insert_books(connection, _START + timedelta(minutes=15 * bar), bar)


def _create_tables(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        "CREATE TABLE canonical_trade_5m_bars ("
        "symbol VARCHAR, bar_open_at TIMESTAMPTZ, open DOUBLE, high DOUBLE, "
        "low DOUBLE, close DOUBLE, volume DOUBLE, trade_count BIGINT)"
    )
    connection.execute(
        "CREATE TABLE replay_book_snapshots ("
        "symbol VARCHAR, ts_exchange_ms BIGINT, ts_utc TIMESTAMPTZ, "
        "best_bid DOUBLE, best_ask DOUBLE)"
    )


def _insert_trade_bar(
    connection: duckdb.DuckDBPyConnection,
    timestamp: datetime,
    offset: int,
) -> None:
    position = offset // 5
    connection.execute(
        "INSERT INTO canonical_trade_5m_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "BTC",
            timestamp,
            100.0 + position,
            101.0 + position,
            99.0 + position,
            100.5 + position,
            1.0,
            1,
        ],
    )


def _insert_books(
    connection: duckdb.DuckDBPyConnection,
    bar_open: datetime,
    bar: int,
) -> None:
    seconds = [1, *range(6, 897, 5), 899]
    denominator = len(seconds) - 1
    rows = []
    for position, second in enumerate(seconds):
        fraction = position / denominator
        bid = 99.9 + bar + 2.5 * fraction
        rows.append((second, bid, bid + 0.2))
    for seconds, bid, ask in rows:
        timestamp = bar_open + timedelta(seconds=seconds)
        connection.execute(
            "INSERT INTO replay_book_snapshots VALUES (?, ?, ?, ?, ?)",
            ["BTC", int(timestamp.timestamp() * 1000), timestamp, bid, ask],
        )
