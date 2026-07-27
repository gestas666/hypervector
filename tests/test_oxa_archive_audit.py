"""Tests for end-to-end 0xArchive bundle auditing."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    audit_oxa_archive,
)
from hypervector.data.oxa_history import OxaBookRequest, output_directory
from hypervector.data.oxa_trades import OxaTradeRequest, trade_output_directory


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
        counts={"row_count": 12, "coalesced_same_ms": 2},
    )
    _write_bundle(
        trade_output_directory(tmp_path, trade),
        source="0xarchive_hyperliquid_public_trades",
        config=config,
        counts={"trade_count": 7, "raw_fill_count": 14},
    )

    report = audit_oxa_archive(config)

    assert report.complete is True
    assert report.present_bundles == 2
    assert report.book_snapshots == 12
    assert report.public_trades == 7
    assert report.raw_participant_fills == 14
    assert report.coalesced_book_snapshots == 2
    assert report.evidence_bytes == 16


def _write_bundle(
    directory: Path,
    *,
    source: str,
    config: OxaArchiveAuditConfig,
    counts: dict[str, int],
) -> None:
    directory.mkdir(parents=True)
    evidence = directory / "evidence.bin"
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
    manifest.update(counts)
    (directory / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
