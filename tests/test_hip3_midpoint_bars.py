"""Causal HIP-3 midpoint-bar construction contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from hypervector.research.hip3_midpoint_bars import build_hip3_midpoint_bars


def _database(path: Path) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            CREATE TABLE archive_bundles (
                bundle_id VARCHAR,
                symbol VARCHAR,
                start_utc TIMESTAMPTZ,
                end_utc TIMESTAMPTZ,
                book_rows BIGINT
            );
            CREATE TABLE archive_bundle_provenance (
                bundle_id VARCHAR,
                market_family VARCHAR,
                book_only BOOLEAN
            );
            CREATE TABLE replay_book_snapshots (
                symbol VARCHAR,
                ts_exchange_ms BIGINT,
                ts_utc TIMESTAMPTZ,
                best_bid DOUBLE,
                best_ask DOUBLE,
                mid_price DOUBLE,
                micro_price DOUBLE,
                spread_bps DOUBLE,
                imbalance_5 DOUBLE,
                imbalance_10 DOUBLE
            );
            """
        )
        connection.execute(
            "INSERT INTO archive_bundles VALUES (?, ?, ?, ?, ?)",
            ["bundle", "xyz:SP500", start, start + timedelta(minutes=45), 4],
        )
        connection.execute(
            "INSERT INTO archive_bundle_provenance VALUES (?, ?, ?)",
            ["bundle", "hip3", True],
        )
        rows = (
            (
                "xyz:SP500",
                1_767_225_601_000,
                start + timedelta(seconds=1),
                99.0,
                101.0,
                100.0,
                100.2,
                2.0,
                0.1,
                0.2,
            ),
            (
                "xyz:SP500",
                1_767_225_900_000,
                start + timedelta(minutes=5),
                101.0,
                103.0,
                102.0,
                102.2,
                1.9,
                0.3,
                0.4,
            ),
            (
                "xyz:SP500",
                1_767_226_499_000,
                start + timedelta(minutes=14, seconds=59),
                98.0,
                100.0,
                99.0,
                99.2,
                2.1,
                0.5,
                0.6,
            ),
            (
                "xyz:SP500",
                1_767_227_401_000,
                start + timedelta(minutes=30, seconds=1),
                104.0,
                106.0,
                105.0,
                105.2,
                1.8,
                -0.1,
                -0.2,
            ),
        )
        connection.executemany(
            "INSERT INTO replay_book_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def test_builds_causal_ohlc_and_retains_observable_gap(tmp_path: Path) -> None:
    database = tmp_path / "hip3.duckdb"
    _database(database)

    result = build_hip3_midpoint_bars(database, symbol="xyz:SP500")

    assert result.symbol == "xyz:SP500"
    assert result.archive_bundles == 1
    assert result.archive_book_rows == 4
    assert len(result.bars) == 2
    first = result.bars.iloc[0]
    assert first[["open", "high", "low", "close"]].tolist() == [
        100.0,
        102.0,
        99.0,
        99.0,
    ]
    assert first["source_snapshot_count"] == 3
    assert first["first_boundary_delay_ms"] == 1_000
    assert first["end_boundary_age_ms"] == 1_000
    assert first["maximum_snapshot_interval_ms"] == 599_000
    assert first["entry_bid"] == 99.0
    assert first["entry_ask"] == 101.0
    assert first["decision_bid"] == 98.0
    assert first["decision_ask"] == 100.0
    assert first["decision_micro_price"] == 99.2
    assert first["decision_spread_bps"] == 2.1
    assert first["decision_imbalance_5"] == 0.5
    assert first["decision_imbalance_10"] == 0.6
    assert result.bars["gap_before_bars"].tolist() == [0, 1]
    assert result.missing_bar_count == 1
    assert str(result.bars.index.tz) == "UTC"


def test_rejects_non_hip3_or_incomplete_archive_provenance(tmp_path: Path) -> None:
    database = tmp_path / "hip3.duckdb"
    _database(database)
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "UPDATE archive_bundle_provenance SET market_family = 'native'"
        )

    with pytest.raises(ValueError, match="complete HIP-3 provenance"):
        build_hip3_midpoint_bars(database, symbol="xyz:SP500")


def test_accepts_checksum_ingested_paired_hip3_provenance(tmp_path: Path) -> None:
    database = tmp_path / "paired.duckdb"
    _database(database)
    with duckdb.connect(str(database)) as connection:
        connection.execute("UPDATE archive_bundle_provenance SET book_only = false")

    result = build_hip3_midpoint_bars(database, symbol="xyz:SP500")

    assert result.archive_bundles == 1
    assert result.archive_book_rows == 4


def test_explicit_scope_excludes_later_checksum_complete_bundles(
    tmp_path: Path,
) -> None:
    database = tmp_path / "scoped.duckdb"
    _database(database)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "INSERT INTO archive_bundles VALUES (?, ?, ?, ?, ?)",
            [
                "later",
                "xyz:SP500",
                start + timedelta(minutes=45),
                start + timedelta(hours=1),
                1,
            ],
        )
        connection.execute(
            "INSERT INTO archive_bundle_provenance VALUES (?, ?, ?)",
            ["later", "hip3", False],
        )
        connection.execute(
            """
            INSERT INTO replay_book_snapshots VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "xyz:SP500",
                1_767_228_301_000,
                start + timedelta(minutes=45, seconds=1),
                106.0,
                108.0,
                107.0,
                107.2,
                1.8,
                0.1,
                0.2,
            ],
        )

    result = build_hip3_midpoint_bars(
        database,
        symbol="xyz:SP500",
        start_utc=pd.Timestamp(start),
        end_utc=pd.Timestamp(start + timedelta(minutes=45)),
    )

    assert result.archive_start_utc == pd.Timestamp(start)
    assert result.archive_end_utc == pd.Timestamp(start + timedelta(minutes=45))
    assert result.archive_bundles == 1
    assert result.archive_book_rows == 4


def test_excludes_partial_terminal_bucket(tmp_path: Path) -> None:
    database = tmp_path / "partial.duckdb"
    _database(database)
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "UPDATE archive_bundles SET end_utc = end_utc - INTERVAL '5 minutes'"
        )

    result = build_hip3_midpoint_bars(database, symbol="xyz:SP500")

    assert result.archive_end_utc.minute == 40
    assert result.bars.index.tolist() == [result.archive_start_utc]
    assert result.expected_bar_count == 2
    assert result.missing_bar_count == 1


def test_rejects_unqualified_symbol_before_query(tmp_path: Path) -> None:
    database = tmp_path / "hip3.duckdb"
    _database(database)

    with pytest.raises(ValueError, match="HIP-3 symbol"):
        build_hip3_midpoint_bars(database, symbol="SP500")


def test_rejects_crossed_executable_boundary_quotes(tmp_path: Path) -> None:
    """A malformed source book cannot become a success-shaped bar."""
    database = tmp_path / "crossed.duckdb"
    _database(database)
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            """
            UPDATE replay_book_snapshots
            SET best_bid = 102.0, best_ask = 101.0
            WHERE ts_exchange_ms = 1767225601000
            """
        )

    with pytest.raises(ValueError, match="executable quotes"):
        build_hip3_midpoint_bars(database, symbol="xyz:SP500")
