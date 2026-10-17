"""Regression: incremental DuckDB builds after repairs, without re-hashing history.

* A changed (repaired) bundle names its window and directories and points at
  ``--replace-changed``; the build handler can apply it through
  ``replace_changed_archive``.
* Already-ingested bundles whose manifest fingerprint matches are skipped
  before any per-file checksum work; ``verify_all`` restores the full audit.
* Every pending bundle is still checksum-verified before any database write.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hypervector.cli_oxa import cmd_research_db_build
from hypervector.data import oxa_archive_audit
from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    verified_archive_bundles,
)
from hypervector.data.oxa_history import (
    OxaBookRequest,
    OxaHistoryClient,
    fetch_orderbook_history,
    output_directory,
    store_orderbook_history,
)
from hypervector.data.oxa_trades import (
    OxaTradeClient,
    OxaTradeRequest,
    fetch_trade_history,
    store_trade_history,
    trade_output_directory,
)
from hypervector.data.research_database import ResearchDatabase

START = datetime(2026, 7, 26, 0, tzinfo=UTC)
END = START + timedelta(hours=2)


@dataclass
class Reply:
    payload: object
    status_code: int = 200

    def json(self) -> object:
        return self.payload


class OnePage:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def get(self, url: str, **_kwargs: object) -> Reply:
        return Reply(self.payload)


def _z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _store_window(root: Path, start: datetime, trade_id: int) -> None:
    end = start + timedelta(hours=1)
    book_request = OxaBookRequest("BTC", start, end)
    book_payload = {
        "success": True,
        "data": [
            {
                "symbol": "BTC",
                "timestamp": _z(start + timedelta(seconds=1)),
                "bids": [{"px": "65370.0", "sz": "1.0", "n": 1}],
                "asks": [{"px": "65371.0", "sz": "1.0", "n": 1}],
            }
        ],
        "meta": {"request_id": f"book-{trade_id}", "next_cursor": None},
    }
    book = fetch_orderbook_history(
        OxaHistoryClient(api_key="k", session=OnePage(book_payload)), book_request
    )
    store_orderbook_history(root, book_request, book)
    trade_request = OxaTradeRequest("BTC", start, end)
    base = {
        "symbol": "BTC",
        "price": "65370",
        "size": "0.1",
        "timestamp": _z(start + timedelta(seconds=2)),
        "trade_id": trade_id,
    }
    trade_payload = {
        "success": True,
        "data": [
            {**base, "side": "B", "crossed": False},
            {**base, "side": "A", "crossed": True},
        ],
        "meta": {"request_id": f"trade-{trade_id}", "next_cursor": None},
    }
    trades = fetch_trade_history(
        OxaTradeClient(api_key="k", session=OnePage(trade_payload)), trade_request
    )
    store_trade_history(root, trade_request, trades)


@pytest.fixture
def archive(tmp_path: Path) -> OxaArchiveAuditConfig:
    _store_window(tmp_path, START, 7001)
    _store_window(tmp_path, START + timedelta(hours=1), 7002)
    return OxaArchiveAuditConfig("BTC", START, END, tmp_path)


def _trade_dir(config: OxaArchiveAuditConfig, start: datetime) -> Path:
    return trade_output_directory(
        config.data_root, OxaTradeRequest("BTC", start, start + timedelta(hours=1))
    )


def _book_dir(config: OxaArchiveAuditConfig, start: datetime) -> Path:
    return output_directory(
        config.data_root, OxaBookRequest("BTC", start, start + timedelta(hours=1))
    )


def _simulate_repair(directory: Path) -> None:
    """Change manifest bytes the way an explicit source repair does."""
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest["repair"] = {"method": "test_repair"}
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", "utf-8")


def _tamper(directory: Path) -> None:
    page = directory / "raw" / "page-0001.json.gz"
    page.write_bytes(page.read_bytes() + b"tampered")


def _count_file_checks(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    seen: list[Path] = []
    original = oxa_archive_audit.verify_file_evidence

    def counting(bundle: Path, value: object) -> None:
        seen.append(bundle)
        original(bundle, value)

    monkeypatch.setattr(
        "hypervector.data.oxa_archive_audit.verify_file_evidence", counting
    )
    return seen


def test_changed_bundle_error_is_actionable(
    tmp_path: Path, archive: OxaArchiveAuditConfig
) -> None:
    database = ResearchDatabase(tmp_path / "research.duckdb")
    database.ingest_archive(archive)
    trade_dir = _trade_dir(archive, START)
    _simulate_repair(trade_dir)

    with pytest.raises(ValueError, match="different evidence") as raised:
        database.ingest_archive(archive)

    message = str(raised.value)
    assert START.isoformat() in message
    assert (START + timedelta(hours=1)).isoformat() in message
    assert str(trade_dir) in message
    assert str(_book_dir(archive, START)) in message
    assert "--replace-changed" in message


def _build_args(
    config: OxaArchiveAuditConfig, database: Path, **extra: object
) -> argparse.Namespace:
    return argparse.Namespace(
        data_root=config.data_root,
        symbol="BTC",
        start=config.start,
        end=config.end,
        depth=20,
        market_family="core",
        books_only=False,
        database=database,
        **extra,
    )


def test_build_handler_applies_repaired_bundle_with_replace_changed(
    tmp_path: Path,
    archive: OxaArchiveAuditConfig,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "research.duckdb"
    assert cmd_research_db_build(_build_args(archive, path)) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["mode"] == "incremental"
    _simulate_repair(_trade_dir(archive, START))

    assert cmd_research_db_build(_build_args(archive, path)) == 1
    assert "--replace-changed" in capsys.readouterr().err

    assert cmd_research_db_build(_build_args(archive, path, replace_changed=True)) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "replace_changed"
    assert report["ingest"] == {
        "imported_bundles": 1,
        "skipped_bundles": 1,
        "book_rows": 1,
        "trade_rows": 1,
    }
    assert report["summary"]["archive_bundles"] == 2
    assert report["summary"]["source_public_trades"] == 2


def test_incremental_rebuild_skips_checksums_of_ingested_bundles(
    tmp_path: Path,
    archive: OxaArchiveAuditConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _count_file_checks(monkeypatch)
    database = ResearchDatabase(tmp_path / "research.duckdb")

    first = database.ingest_archive(archive)
    assert first.imported_bundles == 2
    assert len(seen) == 4

    seen.clear()
    second = database.ingest_archive(archive)
    assert second.skipped_bundles == 2
    assert seen == []


def test_verify_all_restores_full_checksum_audit(
    tmp_path: Path,
    archive: OxaArchiveAuditConfig,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "research.duckdb"
    database = ResearchDatabase(path)
    database.ingest_archive(archive)
    _tamper(_book_dir(archive, START))

    assert database.ingest_archive(archive).skipped_bundles == 2
    with pytest.raises(ValueError, match="byte count|checksum"):
        database.ingest_archive(archive, verify_all=True)
    assert cmd_research_db_build(_build_args(archive, path, verify_all=True)) == 1
    assert "byte count" in capsys.readouterr().err


def test_pending_bundles_are_verified_before_any_write(
    tmp_path: Path, archive: OxaArchiveAuditConfig
) -> None:
    _tamper(_trade_dir(archive, START + timedelta(hours=1)))
    database = ResearchDatabase(tmp_path / "research.duckdb")

    with pytest.raises(ValueError, match="byte count|checksum"):
        database.ingest_archive(archive)

    assert database.summary()["archive_bundles"] == 0


def test_replay_reader_still_verifies_every_file(
    archive: OxaArchiveAuditConfig,
) -> None:
    assert len(verified_archive_bundles(archive)) == 2
    _tamper(_book_dir(archive, START + timedelta(hours=1)))

    with pytest.raises(ValueError, match="byte count|checksum"):
        verified_archive_bundles(archive)


def test_replace_changed_skips_checksums_of_unchanged_bundles(
    tmp_path: Path,
    archive: OxaArchiveAuditConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = ResearchDatabase(tmp_path / "research.duckdb")
    database.ingest_archive(archive)
    _simulate_repair(_trade_dir(archive, START))
    seen = _count_file_checks(monkeypatch)

    report = database.replace_changed_archive(archive)

    assert report.imported_bundles == 1
    assert report.skipped_bundles == 1
    assert sorted(path.name for path in seen) == sorted(
        [_book_dir(archive, START).name, _trade_dir(archive, START).name]
    )
