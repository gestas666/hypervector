"""Fail-closed replay contracts for live Hyperliquid research evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from hypervector.data.research_database import ResearchDatabase
from hypervector.research.live_replay_context import database_live_replay_context
from hypervector.research.research_database_replay import (
    ResearchReplayConfig,
    live_database_evidence_chunks,
    live_database_replay_coverage,
)

_START = datetime(2026, 7, 29, tzinfo=UTC)
_END = datetime(2026, 7, 29, 1, tzinfo=UTC)


def _database(path: Path) -> None:
    ResearchDatabase(path)
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            INSERT INTO live_event_files VALUES
                ('book', 'BTC', DATE '2026-07-29', 'l2', 'book.parquet',
                 1, 2, 'book-hash', current_timestamp),
                ('trade', 'BTC', DATE '2026-07-29', 'trades', 'trade.parquet',
                 1, 1, 'trade-hash', current_timestamp),
                ('context', 'BTC', DATE '2026-07-29', 'asset_context',
                 'context.parquet', 1, 4, 'context-hash', current_timestamp)
            """
        )
        connection.execute(
            """
            INSERT INTO live_book_snapshots VALUES
                ('BTC', 1785283200500, 1785283200500000000,
                 [struct_pack(n := 1, px := 65000.0, sz := 2.0)],
                 [struct_pack(n := 1, px := 65001.0, sz := 3.0)],
                 'hl_ws_l2', 'book'),
                ('BTC', 1785286799500, 1785286799500000000,
                 [struct_pack(n := 1, px := 65010.0, sz := 4.0)],
                 [struct_pack(n := 1, px := 65011.0, sz := 1.0)],
                 'hl_ws_l2', 'book')
            """
        )
        connection.execute(
            """
            INSERT INTO live_public_trades VALUES
                ('BTC', 'buy', 65001.0, 0.25, '0xabc', 1785283200600,
                 1785283200600000000, 123, 'buyer', 'seller',
                 'hl_ws_trades', 'trade')
            """
        )
        connection.execute(
            """
            INSERT INTO live_asset_contexts VALUES
                ('BTC', 1785283199000, 1785283199000000000,
                 65000.5, 65000.0, 0.00001, 1000.0, 65000.5,
                 'exchange', 'hl_ws_context', 'context'),
                ('BTC', 1785284999000, 1785284999000000000,
                 65005.5, 65005.0, 0.00002, 1000.0, 65005.5,
                 'exchange', 'hl_ws_context', 'context'),
                ('BTC', 1785286799000, 1785286799000000000,
                 65010.5, 65010.0, 0.00003, 1000.0, 65010.5,
                 'exchange', 'hl_ws_context', 'context'),
                ('BTC', 1785286800500, 1785286800500000000,
                 65011.5, 65011.0, 0.00004, 1000.0, 65011.5,
                 'exchange', 'hl_ws_context', 'context')
            """
        )


def test_live_database_replay_reads_native_l2_and_public_trades(
    tmp_path: Path,
) -> None:
    """A bounded live window yields normalized replay evidence."""
    path = tmp_path / "research.duckdb"
    _database(path)
    config = ResearchReplayConfig(path, "BTC", _START, _END)

    chunks = tuple(
        live_database_evidence_chunks(
            config,
            include_trades=True,
            maximum_book_gap_seconds=3_601.0,
        )
    )

    assert len(chunks) == 1
    assert chunks[0].book is not None
    assert chunks[0].trades is not None
    assert chunks[0].book["best_bid"].tolist() == [65_000.0, 65_010.0]
    assert chunks[0].book["obi_5"].iloc[0] == pytest.approx(-0.2)
    assert chunks[0].trades["trade_id"].tolist() == [123]

    coverage = live_database_replay_coverage(
        config,
        include_trades=True,
        maximum_book_gap_seconds=3_601.0,
    )
    assert coverage["data_source"] == "duckdb_live_hyperliquid_events"
    assert coverage["book_snapshots"] == 2
    assert coverage["public_trades"] == 1
    assert coverage["recorded_stream_gaps"] == 0
    assert coverage["maximum_book_gap_seconds"] == pytest.approx(3_599.0)


def test_live_database_replay_keeps_five_and_ten_level_pressure_distinct(
    tmp_path: Path,
) -> None:
    """Five-level OBI is not silently replaced by ten-level pressure."""
    path = tmp_path / "research.duckdb"
    _database(path)
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            UPDATE live_book_snapshots SET
                bids = [
                    struct_pack(n := 1, px := 65000.0, sz := 2.0),
                    struct_pack(n := 1, px := 64999.0, sz := 2.0),
                    struct_pack(n := 1, px := 64998.0, sz := 2.0),
                    struct_pack(n := 1, px := 64997.0, sz := 2.0),
                    struct_pack(n := 1, px := 64996.0, sz := 2.0),
                    struct_pack(n := 1, px := 64995.0, sz := 20.0)
                ],
                asks = [
                    struct_pack(n := 1, px := 65001.0, sz := 1.0),
                    struct_pack(n := 1, px := 65002.0, sz := 1.0),
                    struct_pack(n := 1, px := 65003.0, sz := 1.0),
                    struct_pack(n := 1, px := 65004.0, sz := 1.0),
                    struct_pack(n := 1, px := 65005.0, sz := 1.0),
                    struct_pack(n := 1, px := 65006.0, sz := 1.0)
                ]
            WHERE exchange_ts_ms = 1785283200500
            """
        )
    config = ResearchReplayConfig(path, "BTC", _START, _END)

    chunk = tuple(
        live_database_evidence_chunks(
            config,
            include_trades=False,
            maximum_book_gap_seconds=3_601.0,
        )
    )[0]

    assert chunk.book is not None
    assert chunk.book["obi_5"].iloc[0] == pytest.approx(1.0 / 3.0)
    assert chunk.book["obi_10"].iloc[0] == pytest.approx(24.0 / 36.0)


def test_live_database_replay_rejects_large_recorded_gap(tmp_path: Path) -> None:
    """An explicit live-stream gap cannot be omitted from replay validation."""
    path = tmp_path / "research.duckdb"
    _database(path)
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            INSERT INTO live_stream_gaps VALUES (
                'BTC', 'l2Book,trades,activeAssetCtx', 1785285000000000000,
                'test_disconnect', 1785284000000, 1785288000000, 'book'
            )
            """
        )
    config = ResearchReplayConfig(path, "BTC", _START, _END)

    with pytest.raises(ValueError, match="recorded live-stream gap"):
        tuple(
            live_database_evidence_chunks(
                config,
                include_trades=True,
                maximum_book_gap_seconds=3_601.0,
            )
        )


def test_live_database_context_uses_backward_known_hourly_funding(
    tmp_path: Path,
) -> None:
    """Funding at a boundary comes from the last context known by that boundary."""
    path = tmp_path / "research.duckdb"
    _database(path)

    context, coverage = database_live_replay_context(
        path,
        "BTC",
        _START,
        datetime(2026, 7, 29, 1, 1, tzinfo=UTC),
        maximum_price_gap_seconds=3_601.0,
    )

    assert context.prices["mark_price"].tolist() == [
        65_000.5,
        65_005.5,
        65_010.5,
        65_011.5,
    ]
    assert context.funding.to_dict("records") == [
        {"event_ts_ms": 1_785_286_800_000, "funding_rate": 0.00003}
    ]
    assert coverage["funding_source"] == "live_active_asset_context_backward"
    assert coverage["funding_rows"] == 1


def test_live_context_uses_last_received_value_at_duplicate_exchange_ms(
    tmp_path: Path,
) -> None:
    """Recorder bursts at one exchange millisecond resolve by receipt order."""
    path = tmp_path / "research.duckdb"
    _database(path)
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            INSERT INTO live_asset_contexts VALUES
                ('BTC', 1785284999000, 1785284999500000000,
                 65006.5, 65006.0, 0.000025, 1001.0, 65006.5,
                 'exchange', 'hl_ws_context', 'context-later')
            """
        )

    context, _ = database_live_replay_context(
        path,
        "BTC",
        _START,
        datetime(2026, 7, 29, 1, 1, tzinfo=UTC),
        maximum_price_gap_seconds=3_601.0,
    )

    assert context.prices["mark_price"].tolist() == [
        65_000.5,
        65_006.5,
        65_010.5,
        65_011.5,
    ]


def test_live_database_context_rejects_stale_boundary_rate(tmp_path: Path) -> None:
    """A stale rate is not converted into an apparently authentic settlement."""
    path = tmp_path / "research.duckdb"
    _database(path)

    with pytest.raises(ValueError, match="funding observation is stale"):
        database_live_replay_context(
            path,
            "BTC",
            _START,
            datetime(2026, 7, 29, 1, 1, tzinfo=UTC),
            maximum_price_gap_seconds=3_601.0,
            maximum_funding_age_seconds=0.5,
        )
