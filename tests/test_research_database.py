"""DuckDB research-market database integrity contracts."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from hypervector.cli import main
from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
)
from hypervector.data.oxa_history import OxaBookRequest, output_directory
from hypervector.data.oxa_storage import (
    file_evidence,
    gzip_text_writer,
    write_json,
)
from hypervector.data.oxa_trades import (
    OxaTradeRequest,
    TRADE_NORMALIZATION_VERSION,
    trade_output_directory,
)
from hypervector.data.research_database import ResearchDatabase
from hypervector.research.research_database_replay import (
    ResearchReplayConfig,
    canonical_trade_bars,
    canonical_trade_minute_bars,
    database_evidence_chunks,
)
from hypervector.research.research_evidence_source import maker_replay_evidence


def _archive_config(root: Path) -> OxaArchiveAuditConfig:
    return OxaArchiveAuditConfig(
        "BTC",
        datetime(2026, 7, 26, tzinfo=UTC),
        datetime(2026, 7, 26, 1, tzinfo=UTC),
        root,
    )


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    with gzip_text_writer(path) as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _archive_paths(config: OxaArchiveAuditConfig) -> tuple[Path, Path]:
    book_request = OxaBookRequest(
        config.symbol,
        config.start,
        config.end,
        config.depth,
        1000,
        20,
        30.0,
    )
    trade_request = OxaTradeRequest(
        config.symbol,
        config.start,
        config.end,
        1000,
        500,
        30.0,
    )
    return (
        output_directory(config.data_root, book_request),
        trade_output_directory(config.data_root, trade_request),
    )


def _book_rows() -> list[dict[str, object]]:
    return [
        {
            "asks": [
                {"n": 1, "px": "65001", "sz": "2"},
                {"n": 3, "px": "65002", "sz": "20"},
            ],
            "best_ask": "65001",
            "best_bid": "65000",
            "bids": [
                {"n": 2, "px": "65000", "sz": "3"},
                {"n": 4, "px": "64999", "sz": "10"},
            ],
            "n_asks": 2,
            "n_bids": 2,
            "source": "0xarchive_hyperliquid_native_l2",
            "symbol": "BTC",
            "ts_exchange_ms": 1785024000100,
            "vendor_request_id": "book-request",
        },
        {
            "asks": [{"n": 1, "px": "65002", "sz": "1"}],
            "best_ask": "65002",
            "best_bid": "65001",
            "bids": [{"n": 1, "px": "65001", "sz": "4"}],
            "n_asks": 1,
            "n_bids": 1,
            "source": "0xarchive_hyperliquid_native_l2",
            "symbol": "BTC",
            "ts_exchange_ms": 1785024000200,
            "vendor_request_id": "book-request",
        },
    ]


def _trade_rows() -> list[dict[str, object]]:
    return [
        {
            "aggressor_side": "buy",
            "price": "65001",
            "size": "0.25",
            "source": "0xarchive_hyperliquid_public_trades",
            "symbol": "BTC",
            "trade_id": 101,
            "ts_exchange_ms": 1785024000150,
            "vendor_request_id": "trade-request",
        }
    ]


def _write_manifests(
    config: OxaArchiveAuditConfig,
    book_dir: Path,
    trade_dir: Path,
    books: Path,
    trades: Path,
) -> None:
    identity = {
        "complete": True,
        "symbol": "BTC",
        "requested_start": config.start.isoformat(),
        "requested_end": config.end.isoformat(),
    }
    write_json(
        book_dir / "manifest.json",
        identity
        | {
            "source": "0xarchive_hyperliquid_native_l2",
            "row_count": 2,
            "coalesced_same_ms": 0,
            "files": {books.name: file_evidence(books)},
        },
    )
    write_json(
        trade_dir / "manifest.json",
        identity
        | {
            "source": "0xarchive_hyperliquid_public_trades",
            "normalization_version": TRADE_NORMALIZATION_VERSION,
            "trade_count": 1,
            "raw_fill_count": 2,
            "files": {trades.name: file_evidence(trades)},
        },
    )


def _archive_fixture(root: Path) -> OxaArchiveAuditConfig:
    config = _archive_config(root)
    book_dir, trade_dir = _archive_paths(config)
    book_dir.mkdir(parents=True)
    trade_dir.mkdir(parents=True)
    books = book_dir / "books.jsonl.gz"
    trades = trade_dir / "trades.jsonl.gz"
    _write_rows(books, _book_rows())
    _write_rows(trades, _trade_rows())
    _write_manifests(config, book_dir, trade_dir, books, trades)
    return config


def _add_outer_boundary_and_duplicate_trade(config: OxaArchiveAuditConfig) -> None:
    book_dir, trade_dir = _archive_paths(config)
    books = book_dir / "books.jsonl.gz"
    trades = trade_dir / "trades.jsonl.gz"
    end_ms = int(config.end.timestamp() * 1000)
    books.unlink()
    trades.unlink()
    _write_rows(books, _book_rows() + [_book_rows()[0] | {"ts_exchange_ms": end_ms}])
    _write_rows(trades, _trade_rows() + _trade_rows())
    _write_manifests(config, book_dir, trade_dir, books, trades)
    book_manifest = json.loads((book_dir / "manifest.json").read_text())
    trade_manifest = json.loads((trade_dir / "manifest.json").read_text())
    book_manifest["row_count"] = 3
    trade_manifest["trade_count"] = 2
    write_json(book_dir / "manifest.json", book_manifest)
    write_json(trade_dir / "manifest.json", trade_manifest)


def _rewrite_trade_fixture(
    config: OxaArchiveAuditConfig,
    rows: list[dict[str, object]],
    *,
    declared_count: int | None = None,
) -> None:
    _, trade_dir = _archive_paths(config)
    trades = trade_dir / "trades.jsonl.gz"
    trades.unlink()
    _write_rows(trades, rows)
    manifest_path = trade_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["trade_count"] = len(rows) if declared_count is None else declared_count
    manifest["files"] = {trades.name: file_evidence(trades)}
    write_json(manifest_path, manifest)


def test_verified_archive_ingestion_is_idempotent(tmp_path: Path) -> None:
    config = _archive_fixture(tmp_path)
    database = ResearchDatabase(tmp_path / "research.duckdb")

    first = database.ingest_archive(config)
    second = database.ingest_archive(config)

    assert first.to_dict() == {
        "imported_bundles": 1,
        "skipped_bundles": 0,
        "book_rows": 2,
        "trade_rows": 1,
    }
    assert second.to_dict() == {
        "imported_bundles": 0,
        "skipped_bundles": 1,
        "book_rows": 0,
        "trade_rows": 0,
    }
    assert database.summary() == {
        "archive_bundles": 1,
        "source_book_snapshots": 2,
        "source_public_trades": 1,
        "replay_book_snapshots": 2,
        "replay_public_trades": 1,
        "deduplicated_book_rows": 0,
        "deduplicated_trade_rows": 0,
    }


def test_changed_archive_evidence_requires_explicit_atomic_replacement(
    tmp_path: Path,
) -> None:
    """Changed bundle evidence must fail normal ingest and replace explicitly."""
    config = _archive_fixture(tmp_path)
    path = tmp_path / "research.duckdb"
    database = ResearchDatabase(path)
    database.ingest_archive(config)
    replacement = _trade_rows()[0] | {"trade_id": 202, "price": "65002"}
    _rewrite_trade_fixture(config, [replacement])

    with pytest.raises(ValueError, match="different evidence"):
        database.ingest_archive(config)

    report = database.replace_changed_archive(config)

    assert report.imported_bundles == 1
    with duckdb.connect(str(path), read_only=True) as connection:
        rows = connection.execute(
            "SELECT trade_id, price FROM replay_public_trades"
        ).fetchall()
    assert rows == [(202, 65002.0)]
    assert database.summary()["source_public_trades"] == 1


def test_changed_archive_replacement_rolls_back_on_count_failure(
    tmp_path: Path,
) -> None:
    """A failed changed-evidence replacement must retain the prior bundle."""
    config = _archive_fixture(tmp_path)
    path = tmp_path / "research.duckdb"
    database = ResearchDatabase(path)
    database.ingest_archive(config)
    replacement = _trade_rows()[0] | {"trade_id": 202}
    _rewrite_trade_fixture(config, [replacement], declared_count=2)

    with pytest.raises(ValueError, match="row-count mismatch"):
        database.replace_changed_archive(config)

    with duckdb.connect(str(path), read_only=True) as connection:
        trade_ids = connection.execute(
            "SELECT trade_id FROM replay_public_trades"
        ).fetchall()
    assert trade_ids == [(101,)]


def test_book_depth_and_replay_features_are_materialized(tmp_path: Path) -> None:
    config = _archive_fixture(tmp_path)
    path = tmp_path / "research.duckdb"
    ResearchDatabase(path).ingest_archive(config)

    with duckdb.connect(str(path), read_only=True) as connection:
        row = connection.execute(
            """
            SELECT bids[1].n, bids[1].px, bids[1].sz, bid_depth_5,
                   ask_depth_5, imbalance_5, micro_price, spread_bps
            FROM book_snapshots ORDER BY ts_exchange_ms LIMIT 1
            """
        ).fetchone()

    assert row is not None
    assert row[:5] == (2, 65000.0, 3.0, 13.0, 22.0)
    assert row[5] == pytest.approx(-9.0 / 35.0)
    assert row[6] == pytest.approx(65000.6)
    assert row[7] == pytest.approx(0.15384497042330445)


def test_tampered_archive_is_rejected_before_ingestion(tmp_path: Path) -> None:
    config = _archive_fixture(tmp_path)
    book_dir, _ = _archive_paths(config)
    books = book_dir / "books.jsonl.gz"
    books.write_bytes(books.read_bytes() + b"tampered")
    database = ResearchDatabase(tmp_path / "research.duckdb")

    with pytest.raises(ValueError, match="byte count mismatch"):
        database.ingest_archive(config)

    assert database.summary()["archive_bundles"] == 0


def test_row_count_mismatch_rolls_back_bundle(tmp_path: Path) -> None:
    config = _archive_fixture(tmp_path)
    book_dir, _ = _archive_paths(config)
    manifest_path = book_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["row_count"] = 3
    write_json(manifest_path, manifest)
    database = ResearchDatabase(tmp_path / "research.duckdb")

    with pytest.raises(ValueError, match="row-count mismatch"):
        database.ingest_archive(config)

    assert database.summary() == {
        "archive_bundles": 0,
        "source_book_snapshots": 0,
        "source_public_trades": 0,
        "replay_book_snapshots": 0,
        "replay_public_trades": 0,
        "deduplicated_book_rows": 0,
        "deduplicated_trade_rows": 0,
    }


def test_research_database_build_and_status_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _archive_fixture(tmp_path)
    window = [
        "--symbol",
        "BTC",
        "--start",
        config.start.isoformat(),
        "--end",
        config.end.isoformat(),
    ]

    build_rc = main(["--data-root", str(tmp_path), "research-db-build", *window])
    build_report = json.loads(capsys.readouterr().out)
    status_rc = main(["--data-root", str(tmp_path), "research-db-status"])
    status_report = json.loads(capsys.readouterr().out)

    assert build_rc == 0
    assert build_report["ingest"]["book_rows"] == 2
    assert status_rc == 0
    assert status_report["summary"]["replay_book_snapshots"] == 2
    assert status_report["cohort_live"] == {
        "source_files": 0,
        "events": 0,
        "fills": 0,
        "closed_fills": 0,
        "attributed_fills": 0,
        "close_orders": 0,
        "runs": 0,
    }
    assert status_report["database_path"].endswith("research/market.duckdb")


def test_replay_keeps_unique_boundaries_and_deduplicates_trade_ids(
    tmp_path: Path,
) -> None:
    config = _archive_fixture(tmp_path)
    _add_outer_boundary_and_duplicate_trade(config)

    summary = ResearchDatabase(tmp_path / "research.duckdb")
    summary.ingest_archive(config)

    assert summary.summary() == {
        "archive_bundles": 1,
        "source_book_snapshots": 3,
        "source_public_trades": 2,
        "replay_book_snapshots": 3,
        "replay_public_trades": 1,
        "deduplicated_book_rows": 0,
        "deduplicated_trade_rows": 1,
    }

    chunks = tuple(
        database_evidence_chunks(
            ResearchReplayConfig(
                tmp_path / "research.duckdb",
                "BTC",
                config.start,
                config.end,
            ),
            include_trades=True,
        )
    )
    assert len(chunks) == 1
    assert chunks[0].book is not None
    assert chunks[0].trades is not None
    assert len(chunks[0].book) == 2
    assert len(chunks[0].trades) == 1
    assert chunks[0].book["micro_price"].iloc[0] == pytest.approx(65000.6)
    assert chunks[0].book["obi_5"].iloc[0] == pytest.approx(-9.0 / 35.0)


def test_replay_splits_declared_empty_book_window(tmp_path: Path) -> None:
    """A sub-chunk L2 outage remains visible to portfolio-path replay."""
    first = _archive_fixture(tmp_path)
    second = OxaArchiveAuditConfig(
        first.symbol,
        first.end,
        first.end + timedelta(hours=1),
        tmp_path,
    )
    book_dir, trade_dir = _archive_paths(second)
    book_dir.mkdir(parents=True)
    trade_dir.mkdir(parents=True)
    books = book_dir / "books.jsonl.gz"
    trades = trade_dir / "trades.jsonl.gz"
    _write_rows(books, [])
    second_trade = _trade_rows()[0] | {
        "ts_exchange_ms": int(second.start.timestamp() * 1000) + 150
    }
    _write_rows(trades, [second_trade])
    _write_manifests(second, book_dir, trade_dir, books, trades)
    manifest_path = book_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["row_count"] = 0
    write_json(manifest_path, manifest)
    database_path = tmp_path / "research.duckdb"
    database = ResearchDatabase(database_path)
    database.ingest_archive(first)
    database.ingest_archive(second)
    replay = ResearchReplayConfig(
        database_path,
        "BTC",
        first.start,
        second.end,
        chunk=timedelta(hours=2),
    )

    chunks = tuple(database_evidence_chunks(replay, include_trades=True))

    assert len(chunks) == 2
    assert chunks[0].book is not None
    assert chunks[0].start == pd.Timestamp(first.start)
    assert chunks[0].end == pd.Timestamp(first.end)
    assert chunks[1].book is None
    assert chunks[1].trades is not None
    assert chunks[1].start == pd.Timestamp(second.start)
    assert chunks[1].end == pd.Timestamp(second.end)


def test_canonical_trade_bars_use_deduplicated_venue_trades(tmp_path: Path) -> None:
    config = _archive_fixture(tmp_path)
    _add_outer_boundary_and_duplicate_trade(config)
    path = tmp_path / "research.duckdb"
    ResearchDatabase(path).ingest_archive(config)

    bars = canonical_trade_bars(path, "BTC", config.start, config.end)

    assert len(bars) == 1
    assert bars.index[0].to_pydatetime() == config.start
    assert bars.iloc[0].to_dict() == {
        "open": 65001.0,
        "high": 65001.0,
        "low": 65001.0,
        "close": 65001.0,
        "volume": 0.25,
        "trade_count": 1.0,
    }


def test_canonical_trade_minute_bars_preserve_one_minute_structure(
    tmp_path: Path,
) -> None:
    config = _archive_fixture(tmp_path)
    _, trade_dir = _archive_paths(config)
    trades_path = trade_dir / "trades.jsonl.gz"
    second = _trade_rows()[0] | {
        "trade_id": 102,
        "ts_exchange_ms": _trade_rows()[0]["ts_exchange_ms"] + 60_000,
        "price": "65002",
        "size": "0.5",
    }
    trades_path.unlink()
    _write_rows(trades_path, _trade_rows() + [second])
    manifest_path = trade_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["trade_count"] = 2
    manifest["raw_fill_count"] = 4
    manifest["files"] = {trades_path.name: file_evidence(trades_path)}
    write_json(manifest_path, manifest)
    path = tmp_path / "research.duckdb"
    ResearchDatabase(path).ingest_archive(config)

    bars = canonical_trade_minute_bars(path, "BTC", config.start, config.end)

    assert len(bars) == 2
    assert bars.iloc[0]["close"] == 65001.0
    assert bars.iloc[1]["open"] == 65002.0
    assert bars.iloc[1]["volume"] == 0.5


def test_replay_evidence_prefers_materialized_database(tmp_path: Path) -> None:
    config = _archive_fixture(tmp_path)
    database_path = tmp_path / "research" / "market.duckdb"
    ResearchDatabase(database_path).ingest_archive(config)

    evidence = maker_replay_evidence(
        tmp_path,
        "BTC",
        config.start,
        config.end,
        include_trades=True,
    )
    chunks = tuple(evidence.chunks)

    assert evidence.summary["data_source"] == "duckdb_canonical_replay"
    assert evidence.summary["book_snapshots"] == 2
    assert evidence.summary["public_trades"] == 1
    assert len(chunks) == 1
