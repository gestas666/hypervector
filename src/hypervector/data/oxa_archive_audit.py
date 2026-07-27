"""Whole-window integrity and coverage audit for 0xArchive evidence bundles."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from hypervector.data.oxa_api import validate_symbol, validate_window
from hypervector.data.oxa_history import OxaBookRequest, output_directory
from hypervector.data.oxa_storage import verify_file_evidence
from hypervector.data.oxa_trades import OxaTradeRequest, trade_output_directory


@dataclass(frozen=True)
class OxaArchiveAuditConfig:
    """Expected archive identity, bounds, and hourly bundle dimensions."""

    symbol: str
    start: datetime
    end: datetime
    data_root: Path
    chunk: timedelta = timedelta(hours=1)
    depth: int = 20

    def __post_init__(self) -> None:
        validate_symbol(self.symbol)
        validate_window(self.start, self.end)
        if self.chunk <= timedelta(0):
            raise ValueError("archive audit chunk must be positive")
        if not 1 <= self.depth <= 20:
            raise ValueError("archive audit depth must be between 1 and 20")


@dataclass(frozen=True)
class OxaArchiveAuditReport:
    """Aggregate coverage and checksum evidence for one requested window."""

    complete: bool
    expected_bundles: int
    present_bundles: int
    missing_directories: tuple[str, ...]
    book_snapshots: int
    public_trades: int
    raw_participant_fills: int
    coalesced_book_snapshots: int
    empty_book_windows: int
    empty_trade_windows: int
    evidence_bytes: int

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe audit report."""
        return asdict(self)


@dataclass(frozen=True)
class _BundleStats:
    rows: int
    raw_fills: int
    coalesced: int
    evidence_bytes: int


def audit_oxa_archive(config: OxaArchiveAuditConfig) -> OxaArchiveAuditReport:
    """Verify all expected hourly book/trade manifests and evidence checksums."""
    missing: list[str] = []
    books: list[_BundleStats] = []
    trades: list[_BundleStats] = []
    windows = _iter_windows(config)
    for start, end in windows:
        book_path, trade_path = _bundle_paths(config, start, end)
        _collect_bundle(book_path, "book", config, start, end, books, missing)
        _collect_bundle(trade_path, "trade", config, start, end, trades, missing)
    expected = 2 * len(windows)
    return OxaArchiveAuditReport(
        complete=not missing,
        expected_bundles=expected,
        present_bundles=expected - len(missing),
        missing_directories=tuple(missing),
        book_snapshots=sum(item.rows for item in books),
        public_trades=sum(item.rows for item in trades),
        raw_participant_fills=sum(item.raw_fills for item in trades),
        coalesced_book_snapshots=sum(item.coalesced for item in books),
        empty_book_windows=sum(item.rows == 0 for item in books),
        empty_trade_windows=sum(item.rows == 0 for item in trades),
        evidence_bytes=sum(item.evidence_bytes for item in books + trades),
    )


def _iter_windows(
    config: OxaArchiveAuditConfig,
) -> tuple[tuple[datetime, datetime], ...]:
    windows: list[tuple[datetime, datetime]] = []
    start = config.start
    while start < config.end:
        end = min(start + config.chunk, config.end)
        windows.append((start, end))
        start = end
    return tuple(windows)


def _bundle_paths(
    config: OxaArchiveAuditConfig,
    start: datetime,
    end: datetime,
) -> tuple[Path, Path]:
    book = OxaBookRequest(config.symbol, start, end, config.depth, 1000, 20, 30.0)
    trade = OxaTradeRequest(config.symbol, start, end, 1000, 500, 30.0)
    return (
        output_directory(config.data_root, book),
        trade_output_directory(config.data_root, trade),
    )


def _collect_bundle(
    directory: Path,
    kind: str,
    config: OxaArchiveAuditConfig,
    start: datetime,
    end: datetime,
    output: list[_BundleStats],
    missing: list[str],
) -> None:
    if not directory.is_dir():
        missing.append(str(directory.resolve()))
        return
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"archive bundle has no manifest: {directory}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_identity(manifest, kind, config, start, end, directory)
    verify_file_evidence(directory, manifest.get("files"))
    output.append(_bundle_stats(manifest, kind, directory))


def _validate_identity(
    manifest: object,
    kind: str,
    config: OxaArchiveAuditConfig,
    start: datetime,
    end: datetime,
    directory: Path,
) -> None:
    if not isinstance(manifest, dict):
        raise ValueError(f"archive manifest must be an object: {directory}")
    expected_source = (
        "0xarchive_hyperliquid_native_l2"
        if kind == "book"
        else "0xarchive_hyperliquid_public_trades"
    )
    expected = {
        "complete": True,
        "source": expected_source,
        "symbol": config.symbol,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError(f"archive manifest identity mismatch: {directory}")


def _bundle_stats(
    manifest: dict[str, object], kind: str, directory: Path
) -> _BundleStats:
    row_key = "row_count" if kind == "book" else "trade_count"
    rows = _count(manifest, row_key, directory)
    raw_fills = _count(manifest, "raw_fill_count", directory) if kind == "trade" else 0
    coalesced = (
        _count(manifest, "coalesced_same_ms", directory) if kind == "book" else 0
    )
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError(f"archive manifest has invalid file evidence: {directory}")
    byte_count = sum(_evidence_bytes(value, directory) for value in files.values())
    return _BundleStats(rows, raw_fills, coalesced, byte_count)


def _count(manifest: dict[str, object], key: str, directory: Path) -> int:
    value = manifest.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"archive manifest has invalid {key}: {directory}")
    return value


def _evidence_bytes(value: object, directory: Path) -> int:
    if not isinstance(value, dict):
        raise ValueError(f"archive manifest has invalid file evidence: {directory}")
    byte_count = value.get("bytes")
    if isinstance(byte_count, bool) or not isinstance(byte_count, int):
        raise ValueError(f"archive manifest has invalid evidence bytes: {directory}")
    return byte_count
