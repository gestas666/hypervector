"""Input-contract tests for the OI deleveraging feasibility screen."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

from hypervector.data.live_event_research_sql import LIVE_EVENT_SCHEMA_SQL
from hypervector.data.research_database_sql import SCHEMA_SQL
from hypervector.research.oi_deleveraging_inputs import load_oi_deleveraging_minutes


def _millis(value: datetime) -> int:
    return int(value.timestamp() * 1_000)


def _nanos(value: datetime) -> int:
    return int(value.timestamp() * 1_000_000_000)


def _database(path: Path) -> datetime:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    with duckdb.connect(str(path)) as connection:
        connection.execute(SCHEMA_SQL)
        connection.execute(LIVE_EVENT_SCHEMA_SQL)
        for minute_index in range(2):
            minute = start + timedelta(minutes=minute_index)
            _insert_contexts(connection, minute, minute_index)
            _insert_books(connection, minute, minute_index)
            _insert_trades(connection, minute, minute_index)
        connection.execute(
            "DELETE FROM live_book_snapshots WHERE exchange_ts_ms >= ?",
            [_millis(start + timedelta(minutes=1))],
        )
    return start


def _insert_contexts(
    connection: duckdb.DuckDBPyConnection, minute: datetime, index: int
) -> None:
    for seconds, open_interest in ((1, 1_000.0 + index), (50, 1_010.0 + index)):
        received = minute + timedelta(seconds=seconds)
        connection.execute(
            "INSERT INTO live_asset_contexts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                "BTC",
                _millis(received),
                _nanos(received),
                100.0,
                100.0,
                0.0,
                open_interest,
                100.0,
                "local_receive_no_exchange_timestamp",
                "hyperliquid_ws_activeAssetCtx",
                f"context-{index}-{seconds}",
            ],
        )


def _insert_books(
    connection: duckdb.DuckDBPyConnection, minute: datetime, index: int
) -> None:
    for seconds, bid_size, ask_size in ((2, 3.0, 1.0), (55, 1.0, 3.0)):
        observed = minute + timedelta(seconds=seconds)
        bids = [{"n": 1, "px": 99.0 + index, "sz": bid_size}]
        asks = [{"n": 1, "px": 101.0 + index, "sz": ask_size}]
        connection.execute(
            "INSERT INTO live_book_snapshots VALUES (?,?,?,?,?,?,?)",
            [
                "BTC",
                _millis(observed),
                _nanos(observed),
                bids,
                asks,
                "hyperliquid_ws_l2Book",
                f"book-{index}-{seconds}",
            ],
        )


def _insert_trades(
    connection: duckdb.DuckDBPyConnection, minute: datetime, index: int
) -> None:
    for sequence, (seconds, side, price, size) in enumerate(
        ((3, "buy", 100.0 + index, 2.0), (40, "sell", 101.0 + index, 1.0))
    ):
        observed = minute + timedelta(seconds=seconds)
        connection.execute(
            "INSERT INTO live_public_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                "BTC",
                side,
                price,
                size,
                f"hash-{index}-{sequence}",
                _millis(observed),
                _nanos(observed),
                index * 10 + sequence,
                "buyer",
                "seller",
                "hyperliquid_ws_trades",
                f"trade-{index}-{sequence}",
            ],
        )


def test_loader_uses_causal_last_context_and_exact_book_roles(tmp_path: Path) -> None:
    database = tmp_path / "events.duckdb"
    start = _database(database)

    rows = load_oi_deleveraging_minutes(
        database, "BTC", start, start + timedelta(minutes=2)
    )

    assert len(rows) == 1
    row = rows.iloc[0]
    assert row["minute"] == start
    assert row["open_interest"] == 1_010.0
    assert row["close"] == 101.0
    assert row["first_bid"] == 99.0
    assert row["first_ask"] == 101.0
    assert row["first_quote_at"] == start + timedelta(seconds=2)
    assert row["book_imbalance"] == -0.5
    expected_flow = (200.0 - 101.0) / (200.0 + 101.0)
    assert abs(row["trade_imbalance"] - expected_flow) < 1e-12
