"""DuckDB contracts for verified, book-only HIP-3 market evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from hypervector.cli import main
from hypervector.data.oxa_archive_audit import OxaArchiveAuditConfig
from hypervector.data.oxa_history import (
    OxaBookFetch,
    OxaBookPage,
    OxaBookRequest,
    OxaBookSnapshot,
    OxaLevel,
    store_orderbook_history,
)
from hypervector.data.research_database import ResearchDatabase


_SYMBOL = "xyz:SPCX"
_START = datetime(2026, 8, 6, 14, tzinfo=UTC)
_END = datetime(2026, 8, 6, 15, tzinfo=UTC)


def _hip3_archive(root: Path) -> OxaArchiveAuditConfig:
    request = OxaBookRequest(
        _SYMBOL,
        _START,
        _END,
        depth=2,
        market_family="hip3",
    )
    snapshot = OxaBookSnapshot(
        symbol=_SYMBOL,
        timestamp="2026-08-06T14:00:00.500Z",
        ts_exchange_ms=1_786_021_200_500,
        bids=(OxaLevel("6317.0", "3.0", 2),),
        asks=(OxaLevel("6317.1", "2.0", 1),),
    )
    page = OxaBookPage("hip3-request", None, (snapshot,), 0, {"success": True})
    fetched = OxaBookFetch((page,), (snapshot,), True, None, 0)
    store_orderbook_history(root, request, fetched)
    return OxaArchiveAuditConfig(
        symbol=_SYMBOL,
        start=_START,
        end=_END,
        data_root=root,
        depth=2,
        market_family="hip3",
        book_only=True,
    )


def test_verified_hip3_books_ingest_without_fabricated_trades(tmp_path: Path) -> None:
    config = _hip3_archive(tmp_path)
    path = tmp_path / "research.duckdb"
    database = ResearchDatabase(path)

    first = database.ingest_archive(config)
    second = database.ingest_archive(config)

    assert first.to_dict() == {
        "imported_bundles": 1,
        "skipped_bundles": 0,
        "book_rows": 1,
        "trade_rows": 0,
    }
    assert second.skipped_bundles == 1
    with duckdb.connect(str(path), read_only=True) as connection:
        books = connection.execute(
            "SELECT symbol, source FROM replay_book_snapshots"
        ).fetchall()
        trades = connection.execute("SELECT count(*) FROM public_trades").fetchone()
        provenance = connection.execute(
            "SELECT market_family, book_only FROM archive_bundle_provenance"
        ).fetchone()
    assert books == [(_SYMBOL, "0xarchive_hyperliquid_hip3_l2")]
    assert trades == (0,)
    assert provenance == ("hip3", True)


def test_research_database_cli_accepts_explicit_hip3_book_only_mode(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _hip3_archive(tmp_path)

    rc = main(
        [
            "--data-root",
            str(tmp_path),
            "research-db-build",
            "--symbol",
            _SYMBOL,
            "--start",
            _START.isoformat(),
            "--end",
            _END.isoformat(),
            "--depth",
            "2",
            "--market-family",
            "hip3",
            "--books-only",
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert report["ingest"]["book_rows"] == 1
    assert report["ingest"]["trade_rows"] == 0


def test_reopening_legacy_database_backfills_core_archive_provenance(
    tmp_path: Path,
) -> None:
    path = tmp_path / "research.duckdb"
    ResearchDatabase(path)
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            INSERT INTO archive_bundles (
                bundle_id, symbol, start_utc, end_utc, depth, book_rows,
                trade_rows, book_manifest_sha256, trade_manifest_sha256,
                fingerprint
            ) VALUES (
                'legacy', 'BTC', TIMESTAMPTZ '2026-08-06T14:00:00Z',
                TIMESTAMPTZ '2026-08-06T15:00:00Z', 20, 0, 0,
                'book-sha', 'trade-sha', 'fingerprint'
            )
            """
        )

    ResearchDatabase(path)

    with duckdb.connect(str(path), read_only=True) as connection:
        provenance = connection.execute(
            """
            SELECT market_family, book_only, book_source
            FROM archive_bundle_provenance WHERE bundle_id = 'legacy'
            """
        ).fetchone()
    assert provenance == (
        "core",
        False,
        "0xarchive_hyperliquid_native_l2",
    )


def test_reopening_database_migrates_obsolete_hip3_book_only_constraint(
    tmp_path: Path,
) -> None:
    path = tmp_path / "research.duckdb"
    ResearchDatabase(path)
    with duckdb.connect(str(path)) as connection:
        connection.execute("DROP TABLE archive_bundle_provenance")
        connection.execute(
            """
            CREATE TABLE archive_bundle_provenance (
                bundle_id VARCHAR PRIMARY KEY,
                market_family VARCHAR NOT NULL,
                book_only BOOLEAN NOT NULL,
                book_source VARCHAR NOT NULL,
                CHECK (market_family IN ('core', 'hip3')),
                CHECK (market_family != 'hip3' OR book_only)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO archive_bundle_provenance
            VALUES ('existing', 'hip3', true, '0xarchive_hyperliquid_hip3_l2')
            """
        )

    ResearchDatabase(path)

    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            INSERT INTO archive_bundle_provenance
            VALUES ('paired', 'hip3', false, '0xarchive_hyperliquid_hip3_l2')
            """
        )
        rows = connection.execute(
            """
            SELECT bundle_id, book_only
            FROM archive_bundle_provenance
            ORDER BY bundle_id
            """
        ).fetchall()
    assert rows == [("existing", True), ("paired", False)]
