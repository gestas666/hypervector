"""Sparse-database parity tests for BTC absorption lifecycle replay."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from hypervector.research.btc_subminute_absorption_database_replay import (
    replay_btc_absorption_from_database,
)
from hypervector.research.btc_subminute_absorption_replay import (
    replay_btc_absorption_signals,
)


_START = pd.Timestamp("2026-01-01T00:00:00Z")
_START_MS = int(_START.timestamp() * 1_000)


def _levels(best: float, step: float) -> list[dict[str, float | int]]:
    """Return two archived depth levels."""
    return [
        {"n": 1, "px": best, "sz": 100.0},
        {"n": 1, "px": best + step, "sz": 100.0},
    ]


def _books() -> pd.DataFrame:
    """Return entry, irrelevant, and fixed-target books."""
    rows: list[dict[str, object]] = []
    for offset, bid, ask in (
        (500, 100.0, 100.1),
        (30_000, 100.2, 100.3),
        (60_000, 100.7006, 100.8),
    ):
        rows.append(
            {
                "symbol": "BTC",
                "ts_exchange_ms": _START_MS + offset,
                "ts_utc": pd.to_datetime(_START_MS + offset, unit="ms", utc=True),
                "best_bid": bid,
                "best_ask": ask,
                "bids": _levels(bid, -0.1),
                "asks": _levels(ask, 0.1),
                "mid_price": (bid + ask) / 2.0,
            }
        )
    return pd.DataFrame(rows)


def _database(path: Path, books: pd.DataFrame) -> None:
    """Create minimal archived relations for sparse replay."""
    with duckdb.connect(str(path)) as connection:
        connection.register("book_frame", books)
        connection.execute("CREATE TABLE book_snapshots AS SELECT * FROM book_frame")
        connection.execute(
            """
            CREATE TABLE archive_bundles (
                bundle_id VARCHAR, symbol VARCHAR, start_utc TIMESTAMPTZ
            );
            INSERT INTO archive_bundles VALUES (
                'bundle', 'BTC', TIMESTAMPTZ '2026-01-01T00:00:00Z'
            );
            CREATE TABLE public_trades (
                symbol VARCHAR, trade_id BIGINT, ts_exchange_ms BIGINT,
                price DOUBLE, bundle_id VARCHAR
            );
            """
        )


def _signal() -> pd.DataFrame:
    """Return one database-replay signal."""
    return pd.DataFrame(
        [
            {
                "event_id": "event",
                "arm": "sell_flow_absorption_candidate",
                "symbol": "BTC",
                "side": "long",
                "available_at_utc": _START,
            }
        ]
    )


def test_sparse_database_replay_matches_in_memory_target_economics(
    tmp_path: Path,
) -> None:
    """Sparse SQL path selection must reproduce the reference replay exactly."""
    books = _books()
    database = tmp_path / "market.duckdb"
    _database(database, books)
    trades = pd.DataFrame(columns=["trade_id", "ts_exchange_ms", "price"])
    funding = pd.Series([0.0], index=pd.DatetimeIndex([_START]), name="funding_rate")

    expected = replay_btc_absorption_signals(_signal(), books, trades, funding)
    observed = replay_btc_absorption_from_database(database, _signal(), funding)

    pd.testing.assert_frame_equal(observed.trades, expected.trades)
    assert observed.rejections == expected.rejections
    assert observed.execution_authority == "none"
    assert observed.orders_attempted is False
