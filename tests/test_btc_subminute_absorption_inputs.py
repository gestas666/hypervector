"""Causal input contracts for BTC subminute absorption research."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from hypervector.research.btc_subminute_absorption_inputs import (
    BtcAbsorptionWindow,
    load_btc_absorption_inputs,
)


_START = datetime(2025, 1, 2, tzinfo=UTC)
_END = datetime(2025, 1, 2, 0, 1, tzinfo=UTC)
_BUCKET_MS = int(_START.timestamp() * 1_000)


def _create_database(path: Path, *, stale_anchor: bool = False) -> None:
    """Create one minimal archived BTC event with a duplicate public trade."""
    with duckdb.connect(str(path)) as connection:
        _create_schema(connection)
        _insert_bundle(connection)
        _insert_books(connection)
        _insert_trades(connection)
        anchor = "2025-01-01T22:58:00Z" if stale_anchor else "2025-01-01T23:00:00Z"
        connection.execute(
            """
            INSERT INTO public_trades VALUES (
                'BTC', 99, epoch_ms(CAST(? AS TIMESTAMPTZ)),
                CAST(? AS TIMESTAMPTZ), 'buy', 100.0, 1.0, 'bundle'
            )
            """,
            [anchor, anchor],
        )


def _create_schema(connection: duckdb.DuckDBPyConnection) -> None:
    """Create only the relations required by the bounded extractor."""
    connection.execute(
        """
        CREATE TABLE archive_bundles (
            bundle_id VARCHAR,
            symbol VARCHAR,
            start_utc TIMESTAMPTZ,
            end_utc TIMESTAMPTZ,
            depth INTEGER,
            book_rows BIGINT,
            trade_rows BIGINT,
            book_manifest_sha256 VARCHAR,
            trade_manifest_sha256 VARCHAR,
            fingerprint VARCHAR
        );
        CREATE TABLE book_snapshots (
            symbol VARCHAR,
            ts_exchange_ms BIGINT,
            ts_utc TIMESTAMPTZ,
            bid_depth_10 DOUBLE,
            imbalance_10 DOUBLE,
            mid_price DOUBLE,
            spread_bps DOUBLE,
            bundle_id VARCHAR
        );
        CREATE TABLE public_trades (
            symbol VARCHAR,
            trade_id BIGINT,
            ts_exchange_ms BIGINT,
            ts_utc TIMESTAMPTZ,
            aggressor_side VARCHAR,
            price DOUBLE,
            size DOUBLE,
            bundle_id VARCHAR
        );
        CREATE TABLE canonical_trade_1m_bars (
            symbol VARCHAR,
            bar_open_at TIMESTAMPTZ,
            close DOUBLE
        );
        """
    )


def _insert_bundle(connection: duckdb.DuckDBPyConnection) -> None:
    """Insert one deterministic source-identity row."""
    connection.execute(
        """
        INSERT INTO archive_bundles VALUES (
            'bundle', 'BTC', TIMESTAMPTZ '2025-01-02T00:00:00Z',
            TIMESTAMPTZ '2025-01-02T00:01:00Z', 20, 5, 4,
            'book-sha', 'trade-sha', 'fingerprint'
        )
        """
    )


def _insert_books(connection: duckdb.DuckDBPyConnection) -> None:
    """Insert a depletion-and-recovery path inside one ten-second bucket."""
    rows = (
        (500, 100.0, 102.00, -0.2),
        (2_000, 80.0, 101.99, -0.1),
        (4_000, 70.0, 101.98, 0.0),
        (6_000, 90.0, 101.97, 0.1),
        (8_000, 95.0, 101.98, 0.2),
    )
    for offset, depth, mid, imbalance in rows:
        timestamp_ms = _BUCKET_MS + offset
        connection.execute(
            """
            INSERT INTO book_snapshots VALUES (
                'BTC', ?, to_timestamp(? / 1000.0), ?, ?, ?, 3.0, 'bundle'
            )
            """,
            [timestamp_ms, timestamp_ms, depth, imbalance, mid],
        )


def _insert_trades(connection: duckdb.DuckDBPyConnection) -> None:
    """Insert sell flow, one exact duplicate, and one boundary trade."""
    rows = (
        (1, 1_000, "sell", 100.0, 60_000.0),
        (1, 1_000, "sell", 100.0, 60_000.0),
        (2, 2_000, "buy", 100.0, 10_000.0),
        (3, 10_000, "sell", 100.0, 200_000.0),
    )
    for trade_id, offset, side, price, size in rows:
        timestamp_ms = _BUCKET_MS + offset
        connection.execute(
            """
            INSERT INTO public_trades VALUES (
                'BTC', ?, ?, to_timestamp(? / 1000.0), ?, ?, ?, 'bundle'
            )
            """,
            [trade_id, timestamp_ms, timestamp_ms, side, price, size],
        )


def test_load_inputs_is_causal_deduplicated_and_epoch_aligned(tmp_path: Path) -> None:
    """Duplicate and exact-end trades must not inflate the completed bucket."""
    database = tmp_path / "market.duckdb"
    _create_database(database)

    result = load_btc_absorption_inputs(
        database,
        BtcAbsorptionWindow(_START, _END),
    )

    assert len(result.features) == 1
    row = result.features.iloc[0]
    assert row["bucket_start_utc"].isoformat() == "2025-01-02T00:00:00+00:00"
    assert row["available_at_utc"].isoformat() == "2025-01-02T00:00:10+00:00"
    assert row["snapshot_count"] == 5
    assert row["sell_notional_usd"] == pytest.approx(6_000_000.0)
    assert row["sell_share"] == pytest.approx(6.0 / 7.0)
    assert row["adverse_midpoint_bps"] == pytest.approx(1.9607843137)
    assert row["bid_depletion_fraction"] == pytest.approx(0.3)
    assert row["bid_recovery_fraction"] == pytest.approx(25.0 / 30.0)
    assert row["terminal_imbalance_10"] == pytest.approx(0.2)
    assert row["prior_60m_trend_bps"] == pytest.approx(198.0)


def test_stale_prior_anchor_is_excluded_without_success_fallback(
    tmp_path: Path,
) -> None:
    """A stale trend anchor must yield no usable event rather than zero-fill."""
    database = tmp_path / "market.duckdb"
    _create_database(database, stale_anchor=True)

    result = load_btc_absorption_inputs(
        database,
        BtcAbsorptionWindow(_START, _END),
    )

    assert result.features.empty
    assert result.rejections == {"prior_60m_anchor_stale_or_missing": 1}


def test_zero_depletion_has_zero_recovery_instead_of_nonfinite_value(
    tmp_path: Path,
) -> None:
    """No-depletion control rows must remain usable and fail candidate logic later."""
    database = tmp_path / "market.duckdb"
    _create_database(database)
    with duckdb.connect(str(database)) as connection:
        connection.execute("UPDATE book_snapshots SET bid_depth_10=100.0")

    result = load_btc_absorption_inputs(
        database,
        BtcAbsorptionWindow(_START, _END),
    )

    assert result.features.iloc[0]["bid_depletion_fraction"] == 0.0
    assert result.features.iloc[0]["bid_recovery_fraction"] == 0.0


def test_source_identity_changes_when_registered_bundle_changes(tmp_path: Path) -> None:
    """Bundle evidence mutation must be visible to preregistration validation."""
    database = tmp_path / "market.duckdb"
    _create_database(database)
    window = BtcAbsorptionWindow(_START, _END)
    first = load_btc_absorption_inputs(database, window).source
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "UPDATE archive_bundles SET fingerprint='changed' WHERE bundle_id='bundle'"
        )

    second = load_btc_absorption_inputs(database, window).source

    assert first.bundle_identity_sha256 != second.bundle_identity_sha256


def test_input_request_rejects_naive_or_inverted_bounds(tmp_path: Path) -> None:
    """Input windows must be timezone-aware and strictly ordered."""
    database = tmp_path / "market.duckdb"
    _create_database(database)

    with pytest.raises(ValueError, match="timezone-aware"):
        BtcAbsorptionWindow(datetime(2025, 1, 1), _END)
    with pytest.raises(ValueError, match="precede"):
        BtcAbsorptionWindow(_END, _START)
