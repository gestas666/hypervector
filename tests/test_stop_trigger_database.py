"""Tests for public-trade stop-crossing evidence in DuckDB."""

from __future__ import annotations

import duckdb
import pytest

from hypervector.research.stop_trigger_database import first_trade_stop_crossing


def _connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE archive_bundles (
            bundle_id VARCHAR,
            start_utc TIMESTAMPTZ
        );
        CREATE TABLE public_trades (
            symbol VARCHAR,
            trade_id BIGINT,
            ts_exchange_ms BIGINT,
            price DOUBLE,
            bundle_id VARCHAR
        );
        INSERT INTO archive_bundles VALUES
            ('base', TIMESTAMPTZ '2026-01-01 00:00:00+00')
        """
    )
    connection.executemany(
        "INSERT INTO public_trades VALUES (?, ?, ?, ?, 'base')",
        (
            ("SOL", 1, 1_010, 100.0),
            ("SOL", 2, 1_020, 99.0),
            ("SOL", 3, 1_030, 101.0),
            ("SOL", 4, 1_040, 98.0),
        ),
    )
    return connection


def test_crossing_deduplicates_before_applying_price_boundary() -> None:
    """An adverse stale duplicate must not override a newer corrected trade."""
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO archive_bundles VALUES
                ('new', TIMESTAMPTZ '2026-01-02 00:00:00+00');
            INSERT INTO public_trades VALUES
                ('SOL', 2, 1020, 101.0, 'new')
            """
        )
        crossing = first_trade_stop_crossing(
            connection,
            symbol="SOL",
            direction="long",
            stop_price=99.5,
            start_time_ms=1_000,
            end_time_ms=1_050,
        )

    assert crossing is not None
    assert crossing.trade_id == 4
    assert crossing.timestamp_ms == 1_040


def test_long_stop_selects_first_trade_at_or_below_price() -> None:
    """A long stop bound uses the first adverse public trade crossing."""
    with _connection() as connection:
        crossing = first_trade_stop_crossing(
            connection,
            symbol="SOL",
            direction="long",
            stop_price=99.5,
            start_time_ms=1_000,
            end_time_ms=1_050,
        )

    assert crossing is not None
    assert crossing.trade_id == 2
    assert crossing.timestamp_ms == 1_020
    assert crossing.price == pytest.approx(99.0)


def test_short_stop_selects_first_trade_at_or_above_price() -> None:
    """A short stop bound uses the first adverse public trade crossing."""
    with _connection() as connection:
        crossing = first_trade_stop_crossing(
            connection,
            symbol="SOL",
            direction="short",
            stop_price=100.5,
            start_time_ms=1_000,
            end_time_ms=1_050,
        )

    assert crossing is not None
    assert crossing.trade_id == 3
    assert crossing.timestamp_ms == 1_030


def test_crossing_returns_none_without_adverse_trade() -> None:
    """No matching trade is a negative observation, not a technical success."""
    with _connection() as connection:
        crossing = first_trade_stop_crossing(
            connection,
            symbol="SOL",
            direction="long",
            stop_price=90.0,
            start_time_ms=1_000,
            end_time_ms=1_050,
        )

    assert crossing is None


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"direction": "flat"}, "direction"),
        ({"stop_price": 0.0}, "stop_price"),
        ({"start_time_ms": -1}, "start_time_ms"),
        ({"end_time_ms": 1_000}, "end_time_ms"),
    ],
)
def test_crossing_rejects_invalid_contract(
    changes: dict[str, object],
    message: str,
) -> None:
    """Malformed trigger queries fail before returning evidence."""
    values: dict[str, object] = {
        "symbol": "SOL",
        "direction": "long",
        "stop_price": 99.5,
        "start_time_ms": 1_000,
        "end_time_ms": 1_050,
    }
    values.update(changes)
    with _connection() as connection:
        with pytest.raises(ValueError, match=message):
            first_trade_stop_crossing(connection, **values)  # type: ignore[arg-type]
