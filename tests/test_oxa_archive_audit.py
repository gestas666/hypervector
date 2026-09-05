"""Tests for end-to-end 0xArchive bundle auditing."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    audit_oxa_archive,
    verified_archive_bundles,
)
from hypervector.data.oxa_history import OxaBookRequest, output_directory
from hypervector.data.oxa_trades import (
    OxaTradeRequest,
    TRADE_NORMALIZATION_VERSION,
    trade_output_directory,
)


def _config(tmp_path: Path) -> OxaArchiveAuditConfig:
    return OxaArchiveAuditConfig(
        "BTC",
        datetime(2026, 7, 26, tzinfo=UTC),
        datetime(2026, 7, 26, 1, tzinfo=UTC),
        tmp_path,
    )


def test_audit_reports_both_missing_hourly_families(tmp_path: Path) -> None:
    """Absent book and trade bundles remain explicit coverage failures."""
    report = audit_oxa_archive(_config(tmp_path))

    assert report.complete is False
    assert report.expected_bundles == 2
    assert report.present_bundles == 0
    assert len(report.missing_directories) == 2


def test_audit_verifies_complete_hour_and_aggregates_counts(tmp_path: Path) -> None:
    """Valid evidence checksums and manifest counts produce a complete report."""
    config = _config(tmp_path)
    book = OxaBookRequest(
        config.symbol,
        config.start,
        config.end,
        config.depth,
        1000,
        20,
        30.0,
    )
    trade = OxaTradeRequest(config.symbol, config.start, config.end, 1000, 500, 30.0)
    _write_bundle(
        output_directory(tmp_path, book),
        source="0xarchive_hyperliquid_native_l2",
        config=config,
        counts={
            "row_count": 12,
            "coalesced_same_ms": 2,
            "censored_zero_size_snapshots": 3,
        },
    )
    _write_bundle(
        trade_output_directory(tmp_path, trade),
        source="0xarchive_hyperliquid_public_trades",
        config=config,
        counts={"trade_count": 7, "raw_fill_count": 14},
    )

    report = audit_oxa_archive(config)

    assert report.complete is True
    assert report.symbol == "BTC"
    assert report.market_family == "core"
    assert report.requested_start_utc == config.start.isoformat()
    assert report.requested_end_utc == config.end.isoformat()
    assert report.chunk_seconds == 3_600
    assert report.book_only is False
    assert report.present_bundles == 2
    assert report.book_snapshots == 12
    assert report.public_trades == 7
    assert report.raw_participant_fills == 14
    assert report.coalesced_book_snapshots == 2
    assert report.censored_zero_size_book_snapshots == 3
    assert report.evidence_bytes == 16


def test_verified_archive_bundles_return_replay_paths(tmp_path: Path) -> None:
    """Replay discovery returns typed, checksum-verified hourly evidence."""
    config = _config(tmp_path)
    book = OxaBookRequest(
        config.symbol,
        config.start,
        config.end,
        config.depth,
        1000,
        20,
        30.0,
    )
    trade = OxaTradeRequest(config.symbol, config.start, config.end, 1000, 500, 30.0)
    book_dir = output_directory(tmp_path, book)
    trade_dir = trade_output_directory(tmp_path, trade)
    _write_bundle(
        book_dir,
        source="0xarchive_hyperliquid_native_l2",
        config=config,
        counts={"row_count": 0, "coalesced_same_ms": 0},
        evidence_name="books.jsonl",
    )
    _write_bundle(
        trade_dir,
        source="0xarchive_hyperliquid_public_trades",
        config=config,
        counts={"trade_count": 7, "raw_fill_count": 14},
        evidence_name="trades.jsonl.gz",
    )

    bundles = verified_archive_bundles(config)

    assert len(bundles) == 1
    assert bundles[0].start == config.start
    assert bundles[0].end == config.end
    assert bundles[0].book_path is None
    assert bundles[0].trade_path == trade_dir / "trades.jsonl.gz"
    assert bundles[0].book_rows == 0
    assert bundles[0].trade_rows == 7

    report = audit_oxa_archive(config)
    assert report.empty_book_ranges_utc == (
        (config.start.isoformat(), config.end.isoformat()),
    )
    assert report.empty_trade_ranges_utc == ()


def test_verified_archive_bundles_use_manifest_normalized_filename(
    tmp_path: Path,
) -> None:
    """Legacy uncompressed evidence remains replayable when manifest-verified."""
    config = _config(tmp_path)
    book = OxaBookRequest(
        config.symbol,
        config.start,
        config.end,
        config.depth,
        1000,
        20,
        30.0,
    )
    trade = OxaTradeRequest(config.symbol, config.start, config.end, 1000, 500, 30.0)
    book_dir = output_directory(tmp_path, book)
    trade_dir = trade_output_directory(tmp_path, trade)
    _write_bundle(
        book_dir,
        source="0xarchive_hyperliquid_native_l2",
        config=config,
        counts={"row_count": 12, "coalesced_same_ms": 0},
        evidence_name="books.jsonl",
    )
    _write_bundle(
        trade_dir,
        source="0xarchive_hyperliquid_public_trades",
        config=config,
        counts={"trade_count": 7, "raw_fill_count": 14},
        evidence_name="trades.jsonl.gz",
    )

    bundles = verified_archive_bundles(config)

    assert bundles[0].book_path == book_dir / "books.jsonl"


def test_audit_coalesces_adjacent_empty_book_windows(tmp_path: Path) -> None:
    """Consecutive provider gaps are reported as one exact UTC interval."""
    start = datetime(2026, 7, 26, tzinfo=UTC)
    config = OxaArchiveAuditConfig("BTC", start, start + timedelta(hours=2), tmp_path)
    for offset in range(2):
        window_start = start + timedelta(hours=offset)
        window = OxaArchiveAuditConfig(
            "BTC", window_start, window_start + timedelta(hours=1), tmp_path
        )
        book = OxaBookRequest(
            window.symbol,
            window.start,
            window.end,
            window.depth,
            1000,
            20,
            30.0,
        )
        trade = OxaTradeRequest(
            window.symbol, window.start, window.end, 1000, 500, 30.0
        )
        _write_bundle(
            output_directory(tmp_path, book),
            source="0xarchive_hyperliquid_native_l2",
            config=window,
            counts={"row_count": 0, "coalesced_same_ms": 0},
        )
        _write_bundle(
            trade_output_directory(tmp_path, trade),
            source="0xarchive_hyperliquid_public_trades",
            config=window,
            counts={"trade_count": 7, "raw_fill_count": 14},
        )

    report = audit_oxa_archive(config)

    assert report.empty_book_ranges_utc == (
        (config.start.isoformat(), config.end.isoformat()),
    )


def test_audit_rejects_stale_trade_normalization(tmp_path: Path) -> None:
    """Archive replay must fail closed on pre-taker-only trade bundles."""
    config = _config(tmp_path)
    book = OxaBookRequest(
        config.symbol,
        config.start,
        config.end,
        config.depth,
        1000,
        20,
        30.0,
    )
    trade = OxaTradeRequest(config.symbol, config.start, config.end, 1000, 500, 30.0)
    _write_bundle(
        output_directory(tmp_path, book),
        source="0xarchive_hyperliquid_native_l2",
        config=config,
        counts={"row_count": 1, "coalesced_same_ms": 0},
    )
    directory = trade_output_directory(tmp_path, trade)
    _write_bundle(
        directory,
        source="0xarchive_hyperliquid_public_trades",
        config=config,
        counts={"trade_count": 7, "raw_fill_count": 14},
    )
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["normalization_version"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="normalization"):
        verified_archive_bundles(config)


def _write_bundle(
    directory: Path,
    *,
    source: str,
    config: OxaArchiveAuditConfig,
    counts: dict[str, int],
    evidence_name: str = "evidence.bin",
) -> None:
    directory.mkdir(parents=True)
    evidence = directory / evidence_name
    evidence.write_bytes(b"verified")
    manifest: dict[str, object] = {
        "complete": True,
        "source": source,
        "symbol": config.symbol,
        "requested_start": config.start.isoformat(),
        "requested_end": config.end.isoformat(),
        "page_count": 1,
        "files": {
            evidence.name: {
                "bytes": evidence.stat().st_size,
                "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
            }
        },
    }
    if source == "0xarchive_hyperliquid_public_trades":
        manifest["normalization_version"] = TRADE_NORMALIZATION_VERSION
    manifest.update(counts)
    (directory / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
