"""Tests for the OHLCV-only Cipher research database reader."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from hypervector.research.cipher_suite_duckdb import load_cipher_ohlcv


def _database(path: Path, rows: int = 260, symbol: str = "BTC") -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    values = [
        (
            symbol,
            start + timedelta(minutes=5 * index),
            100.0,
            101.0,
            99.0,
            100.5,
            10.0,
            3,
        )
        for index in range(rows)
    ]
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            CREATE TABLE canonical_trade_5m_bars (
                symbol VARCHAR, bar_open_at TIMESTAMPTZ, open DOUBLE,
                high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE,
                trade_count BIGINT
            )
            """
        )
        connection.executemany(
            "INSERT INTO canonical_trade_5m_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            values,
        )


def test_loader_reads_only_bounded_ohlcv_with_warmup_and_lookahead(
    tmp_path: Path,
) -> None:
    """Cipher data access must not require or aggregate trade/L2 relations."""
    database = tmp_path / "market.duckdb"
    _database(database)
    start = datetime(2026, 1, 1, 20, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 20, 50, tzinfo=UTC)

    inputs = load_cipher_ohlcv(
        database, "BTC", start, end, history_bars=240, horizon_bars=4
    )

    assert inputs.bars.iloc[0]["bar_open_at"] == datetime(2026, 1, 1, tzinfo=UTC)
    assert inputs.bars.iloc[-1]["bar_open_at"] == datetime(
        2026, 1, 1, 21, 5, tzinfo=UTC
    )
    assert inputs.bars.columns.tolist() == [
        "bar_open_at",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]


def test_loader_fails_when_required_horizon_is_incomplete(tmp_path: Path) -> None:
    """Missing outcome evidence must fail rather than censor the entire tail."""
    database = tmp_path / "market.duckdb"
    _database(database, rows=250)

    with pytest.raises(ValueError, match="outcome lookahead"):
        load_cipher_ohlcv(
            database,
            "BTC",
            datetime(2026, 1, 1, 20, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 20, 40, tzinfo=UTC),
            history_bars=240,
            horizon_bars=4,
        )


@pytest.mark.parametrize("symbol", ["ETH", "HYPE"])
def test_loader_supports_configured_hulk_cohort_assets(
    tmp_path: Path, symbol: str
) -> None:
    """Configured Hulk routes require the same bounded venue-data contract."""
    database = tmp_path / "market.duckdb"
    _database(database, symbol=symbol)

    inputs = load_cipher_ohlcv(
        database,
        symbol,
        datetime(2026, 1, 1, 20, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 20, 50, tzinfo=UTC),
        history_bars=240,
        horizon_bars=4,
    )

    assert len(inputs.bars) == 254
