"""Tests for timestamp-bounded visible-depth execution from DuckDB."""

from __future__ import annotations

import duckdb
import pytest

from hypervector.research.market_depth_database import market_fill_at_or_after


def _connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE replay_book_snapshots (
            symbol VARCHAR,
            ts_exchange_ms BIGINT,
            bids STRUCT(n INTEGER, px DOUBLE, sz DOUBLE)[],
            asks STRUCT(n INTEGER, px DOUBLE, sz DOUBLE)[]
        )
        """
    )
    rows = (
        (
            "SOL",
            1_005,
            [{"n": 1, "px": 99.0, "sz": 3.0}],
            [
                {"n": 1, "px": 100.0, "sz": 1.0},
                {"n": 2, "px": 101.0, "sz": 2.0},
            ],
        ),
        (
            "SOL",
            1_010,
            [{"n": 1, "px": 98.0, "sz": 3.0}],
            [{"n": 1, "px": 102.0, "sz": 3.0}],
        ),
        (
            "xyz:SPCX",
            2_005,
            [{"n": 1, "px": 4_999.0, "sz": 0.02}],
            [
                {"n": 1, "px": 5_001.0, "sz": 0.01},
                {"n": 2, "px": 5_002.0, "sz": 0.02},
            ],
        ),
    )
    connection.executemany(
        "INSERT INTO replay_book_snapshots VALUES (?, ?, ?, ?)", rows
    )
    return connection


def test_fill_uses_first_snapshot_after_decision_and_walks_visible_side() -> None:
    """Execution must not select an earlier or more favorable later book."""
    with _connection() as connection:
        timed = market_fill_at_or_after(
            connection,
            symbol="SOL",
            event_time_ms=1_000,
            side="buy",
            quantity=2.0,
            maximum_delay_ms=10,
        )

    assert timed.snapshot_time_ms == 1_005
    assert timed.latency_ms == 5
    assert timed.fill.vwap == pytest.approx(100.5)
    assert timed.fill.complete is True


def test_fill_reports_visible_depth_shortfall_without_extrapolation() -> None:
    """Orders larger than the recorded side remain explicitly incomplete."""
    with _connection() as connection:
        timed = market_fill_at_or_after(
            connection,
            symbol="SOL",
            event_time_ms=1_000,
            side="sell",
            quantity=4.0,
            maximum_delay_ms=10,
        )

    assert timed.fill.complete is False
    assert timed.fill.filled_quantity == pytest.approx(3.0)
    assert timed.fill.unfilled_quantity == pytest.approx(1.0)


def test_fill_preserves_exact_hip3_identity_when_family_is_explicit() -> None:
    """HIP-3 replay must query the exact lower-dex and upper-asset identity."""
    with _connection() as connection:
        timed = market_fill_at_or_after(
            connection,
            symbol="xyz:SPCX",
            market_family="hip3",
            event_time_ms=2_000,
            side="buy",
            quantity=0.02,
            maximum_delay_ms=10,
        )

    assert timed.snapshot_time_ms == 2_005
    assert timed.fill.vwap == pytest.approx(5_001.5)
    assert timed.fill.complete is True


def test_fill_rejects_market_family_identity_mismatch() -> None:
    """A namespaced market must not pass through the core replay contract."""
    with _connection() as connection:
        with pytest.raises(ValueError, match="uppercase Hyperliquid asset"):
            market_fill_at_or_after(
                connection,
                symbol="xyz:SPCX",
                market_family="core",
                event_time_ms=2_000,
                side="buy",
                quantity=0.01,
                maximum_delay_ms=10,
            )


def test_fill_rejects_missing_snapshot_inside_latency_contract() -> None:
    """A stale book must fail instead of using future liquidity silently."""
    with _connection() as connection:
        with pytest.raises(LookupError, match="no SOL book snapshot"):
            market_fill_at_or_after(
                connection,
                symbol="SOL",
                event_time_ms=1_000,
                side="buy",
                quantity=1.0,
                maximum_delay_ms=4,
            )


@pytest.mark.parametrize(
    ("event_time_ms", "maximum_delay_ms", "message"),
    [(-1, 10, "event_time_ms"), (1_000, 0, "maximum_delay_ms")],
)
def test_fill_rejects_invalid_time_bounds(
    event_time_ms: int,
    maximum_delay_ms: int,
    message: str,
) -> None:
    """Invalid evidence windows must fail before querying the database."""
    with _connection() as connection:
        with pytest.raises(ValueError, match=message):
            market_fill_at_or_after(
                connection,
                symbol="SOL",
                event_time_ms=event_time_ms,
                side="buy",
                quantity=1.0,
                maximum_delay_ms=maximum_delay_ms,
            )
