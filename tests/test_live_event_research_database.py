"""DuckDB ingestion of immutable live Hyperliquid event evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from hypervector.data.event_archive import EventArchive
from hypervector.data.hl_events import (
    AssetContextEvent,
    BookLevel,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
)
from hypervector.data.research_database import ResearchDatabase
from hypervector.cli import main
from hypervector.research.research_database_replay import canonical_trade_bars


def _trade(received_ts_ns: int) -> PublicTradeEvent:
    return PublicTradeEvent(
        symbol="BTC",
        aggressor_side="buy",
        price=65_001.0,
        size=0.25,
        transaction_hash="0xabc",
        exchange_ts_ms=1_785_139_200_100,
        received_ts_ns=received_ts_ns,
        trade_id=123,
        buyer="buyer",
        seller="seller",
    )


def _write_live_archive(root: Path) -> None:
    first = EventArchive(data_root=root, symbol="BTC", batch_size=10)
    first.append(
        [
            L2SnapshotEvent(
                symbol="BTC",
                exchange_ts_ms=1_785_139_200_000,
                received_ts_ns=1_785_139_200_001_000_000,
                bids=(BookLevel(65_000.0, 2.0, 1),),
                asks=(BookLevel(65_001.0, 3.0, 1),),
            ),
            _trade(1_785_139_200_101_000_000),
            AssetContextEvent(
                symbol="BTC",
                observed_ts_ms=1_785_139_200_200,
                received_ts_ns=1_785_139_200_201_000_000,
                mark_price=65_000.5,
                oracle_price=65_000.0,
                funding_rate_hourly=0.00001,
                open_interest=1_000.0,
                mid_price=65_000.5,
            ),
        ]
    )
    first.record_gap(
        StreamGap(
            symbol="BTC",
            channel="l2Book,trades,activeAssetCtx",
            detected_ts_ns=1_785_139_200_300_000_000,
            reason="test_disconnect",
            previous_exchange_ts_ms=1_785_139_200_100,
            next_exchange_ts_ms=1_785_139_200_400,
        )
    )
    first.flush()
    second = EventArchive(data_root=root, symbol="BTC", batch_size=10)
    second.append([_trade(1_785_139_200_102_000_000)])
    second.flush()


def _insert_archive_trade(database_path: Path, price: float) -> None:
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            """
            INSERT INTO archive_bundles VALUES (
                'bundle', 'BTC', TIMESTAMPTZ '2026-07-27T00:00:00Z',
                TIMESTAMPTZ '2026-07-27T01:00:00Z', 20, 0, 1,
                'book-sha', 'trade-sha', 'fingerprint', current_timestamp
            )
            """
        )
        connection.execute(
            """
            INSERT INTO public_trades VALUES (
                'BTC', 123, 1785139200100,
                TIMESTAMPTZ '2026-07-27T08:00:00.100Z', 'buy',
                ?, 0.25, '0xarchive_hyperliquid', 'request', 'bundle'
            )
            """,
            [price],
        )


def test_live_event_archive_import_is_idempotent_and_canonically_deduplicated(
    tmp_path: Path,
) -> None:
    _write_live_archive(tmp_path)
    database_path = tmp_path / "research" / "market.duckdb"
    database = ResearchDatabase(database_path)

    first = database.ingest_live_event_archive(tmp_path, "BTC")
    second = database.ingest_live_event_archive(tmp_path, "BTC")

    assert first.to_dict() == {
        "source_files": 5,
        "imported_files": 5,
        "skipped_files": 0,
        "l2_rows": 1,
        "trade_rows": 2,
        "asset_context_rows": 1,
        "gap_rows": 1,
    }
    assert second.to_dict() == {
        "source_files": 5,
        "imported_files": 0,
        "skipped_files": 5,
        "l2_rows": 0,
        "trade_rows": 0,
        "asset_context_rows": 0,
        "gap_rows": 0,
    }
    with duckdb.connect(str(database_path), read_only=True) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM live_public_trades),
                (SELECT count(*) FROM replay_live_public_trades),
                (SELECT count(*) FROM live_book_snapshots),
                (SELECT count(*) FROM live_asset_contexts),
                (SELECT count(*) FROM live_stream_gaps)
            """
        ).fetchone()

    assert counts == (2, 1, 1, 1, 1)


def test_live_event_import_advances_append_only_gap_file(tmp_path: Path) -> None:
    _write_live_archive(tmp_path)
    database_path = tmp_path / "research" / "market.duckdb"
    database = ResearchDatabase(database_path)
    database.ingest_live_event_archive(tmp_path, "BTC")
    archive = EventArchive(data_root=tmp_path, symbol="BTC", batch_size=10)
    archive.record_gap(
        StreamGap(
            symbol="BTC",
            channel="l2Book",
            detected_ts_ns=1_785_139_201_300_000_000,
            reason="second_disconnect",
            previous_exchange_ts_ms=1_785_139_201_100,
            next_exchange_ts_ms=1_785_139_201_400,
        )
    )

    report = database.ingest_live_event_archive(tmp_path, "BTC")
    repeated = database.ingest_live_event_archive(tmp_path, "BTC")

    assert report.imported_files == 1
    assert report.skipped_files == 4
    assert report.gap_rows == 1
    assert repeated.imported_files == 0
    with duckdb.connect(str(database_path), read_only=True) as connection:
        file_row = connection.execute(
            "SELECT count(*), max(row_count) FROM live_event_files "
            "WHERE dataset = 'gaps'"
        ).fetchone()
        gaps = connection.execute(
            "SELECT count(*), count(DISTINCT file_id) FROM live_stream_gaps"
        ).fetchone()

    assert file_row == (1, 2)
    assert gaps == (2, 1)


def test_live_event_import_rejects_non_append_gap_change(tmp_path: Path) -> None:
    _write_live_archive(tmp_path)
    database_path = tmp_path / "research" / "market.duckdb"
    database = ResearchDatabase(database_path)
    database.ingest_live_event_archive(tmp_path, "BTC")
    gap_path = next(
        (tmp_path / "cache" / "events" / "hyperliquid" / "BTC").glob("*/gaps.jsonl")
    )
    gap_path.write_text(gap_path.read_text().replace("test_disconnect", "tampered"))

    with pytest.raises(ValueError, match="changed non-append-only"):
        database.ingest_live_event_archive(tmp_path, "BTC")

    with duckdb.connect(str(database_path), read_only=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM live_stream_gaps"
        ).fetchone() == (1,)


def test_canonical_trade_view_deduplicates_verified_archive_live_overlap(
    tmp_path: Path,
) -> None:
    _write_live_archive(tmp_path)
    database_path = tmp_path / "research" / "market.duckdb"
    database = ResearchDatabase(database_path)
    _insert_archive_trade(database_path, 65_001.0)

    database.ingest_live_event_archive(tmp_path, "BTC")

    with duckdb.connect(str(database_path), read_only=True) as connection:
        trade = connection.execute(
            "SELECT count(*), min(source_origin), min(trade_id) "
            "FROM canonical_public_trades"
        ).fetchone()
        bar = connection.execute(
            """
            SELECT count(*), min(open), min(high), min(low), min(close), min(volume)
            FROM canonical_trade_5m_bars
            """
        ).fetchone()

    assert trade == (1, "archive", 123)
    assert bar == (1, 65_001.0, 65_001.0, 65_001.0, 65_001.0, 0.25)


def test_live_import_rejects_conflicting_archive_trade_atomically(
    tmp_path: Path,
) -> None:
    _write_live_archive(tmp_path)
    database_path = tmp_path / "research" / "market.duckdb"
    database = ResearchDatabase(database_path)
    _insert_archive_trade(database_path, 65_002.0)

    with pytest.raises(ValueError, match="conflicting archive/live public-trade"):
        database.ingest_live_event_archive(tmp_path, "BTC")

    with duckdb.connect(str(database_path), read_only=True) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM live_event_files),
                (SELECT count(*) FROM live_public_trades)
            """
        ).fetchone()
    assert counts == (0, 0)


def test_live_event_import_cli_is_explicitly_report_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_live_archive(tmp_path)

    result = main(
        [
            "--data-root",
            str(tmp_path),
            "db",
            "import-events",
            "--symbol",
            "BTC",
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert result == 0
    assert report["report_only"] is True
    assert report["execution_authority"] == "none"
    assert report["ingest"]["trade_rows"] == 2

    status_result = main(["--data-root", str(tmp_path), "db", "status"])
    status = json.loads(capsys.readouterr().out)
    assert status_result == 0
    assert status["live_events"]["source_trade_rows"] == 2
    assert status["live_events"]["canonical_trade_rows"] == 1
    assert status["live_events"]["duplicate_trade_rows"] == 1
    assert status["live_events"]["archive_overlap_trade_rows"] == 0
    assert status["live_events"]["exact_archive_overlap_rows"] == 0
    assert status["live_events"]["canonical_extension_trade_rows"] == 1


def test_canonical_trade_bars_can_use_live_evidence_after_archive_cutoff(
    tmp_path: Path,
) -> None:
    _write_live_archive(tmp_path)
    database_path = tmp_path / "research" / "market.duckdb"
    database = ResearchDatabase(database_path)
    database.ingest_live_event_archive(tmp_path, "BTC")

    bars = canonical_trade_bars(
        database_path,
        "BTC",
        datetime(2026, 7, 27, 8, 0, tzinfo=UTC),
        datetime(2026, 7, 27, 8, 5, tzinfo=UTC),
    )

    assert len(bars) == 1
    assert bars.iloc[0].to_dict() == {
        "open": 65_001.0,
        "high": 65_001.0,
        "low": 65_001.0,
        "close": 65_001.0,
        "volume": 0.25,
        "trade_count": 1.0,
    }
