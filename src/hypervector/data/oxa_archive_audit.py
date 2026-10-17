"""Whole-window integrity and coverage audit for 0xArchive evidence bundles."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from hypervector.data.oxa_api import (
    MarketFamily,
    validate_market_symbol,
    validate_window,
)
from hypervector.data.oxa_history import (
    DEFAULT_BOOK_MAX_PAGES,
    OxaBookRequest,
    output_directory,
)
from hypervector.data.oxa_storage import verify_file_evidence
from hypervector.data.oxa_trades import (
    DEFAULT_TRADE_MAX_PAGES,
    OxaTradeRequest,
    TRADE_NORMALIZATION_VERSION,
    trade_output_directory,
)


@dataclass(frozen=True)
class OxaArchiveAuditConfig:
    """Expected archive identity, bounds, and hourly bundle dimensions."""

    symbol: str
    start: datetime
    end: datetime
    data_root: Path
    chunk: timedelta = timedelta(hours=1)
    depth: int = 20
    market_family: MarketFamily = "core"
    book_only: bool = False

    def __post_init__(self) -> None:
        validate_market_symbol(self.symbol, self.market_family)
        validate_window(self.start, self.end)
        if self.chunk <= timedelta(0):
            raise ValueError("archive audit chunk must be positive")
        if not 1 <= self.depth <= 20:
            raise ValueError("archive audit depth must be between 1 and 20")


@dataclass(frozen=True)
class OxaArchiveBundle:
    """One checksum-verified hourly book/trade evidence pair."""

    start: datetime
    end: datetime
    book_path: Path | None
    trade_path: Path | None
    book_rows: int
    trade_rows: int


@dataclass(frozen=True)
class OxaArchiveBundleEvidence:
    """Identity-validated manifests for one window, before file checksums.

    Each manifest digest is computed from the exact bytes that were parsed, so
    a caller can compare it with a stored fingerprint and only then decide
    whether the per-file checksum work is needed.
    """

    bundle: OxaArchiveBundle
    book_directory: Path
    trade_directory: Path | None
    book_manifest: dict[str, object]
    trade_manifest: dict[str, object] | None
    book_manifest_sha256: str
    trade_manifest_sha256: str | None

    def verify_files(self) -> None:
        """Checksum every evidence file declared by both manifests."""
        verify_file_evidence(self.book_directory, self.book_manifest.get("files"))
        if self.trade_directory is not None and self.trade_manifest is not None:
            verify_file_evidence(
                self.trade_directory, self.trade_manifest.get("files")
            )


@dataclass(frozen=True)
class OxaArchiveAuditReport:
    """Aggregate coverage and checksum evidence for one requested window."""

    symbol: str
    market_family: MarketFamily
    requested_start_utc: str
    requested_end_utc: str
    chunk_seconds: int
    book_only: bool
    complete: bool
    expected_bundles: int
    present_bundles: int
    missing_directories: tuple[str, ...]
    book_snapshots: int
    public_trades: int
    raw_participant_fills: int
    coalesced_book_snapshots: int
    censored_zero_size_book_snapshots: int
    empty_book_windows: int
    empty_trade_windows: int
    empty_book_ranges_utc: tuple[tuple[str, str], ...]
    empty_trade_ranges_utc: tuple[tuple[str, str], ...]
    evidence_bytes: int

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe audit report."""
        return asdict(self)


@dataclass(frozen=True)
class _BundleStats:
    rows: int
    raw_fills: int
    coalesced: int
    censored_zero_size: int
    evidence_bytes: int


def audit_oxa_archive(config: OxaArchiveAuditConfig) -> OxaArchiveAuditReport:
    """Verify all expected hourly book/trade manifests and evidence checksums."""
    missing: list[str] = []
    books: list[_BundleStats] = []
    trades: list[_BundleStats] = []
    empty_books: list[tuple[datetime, datetime]] = []
    empty_trades: list[tuple[datetime, datetime]] = []
    windows = _iter_windows(config)
    for start, end in windows:
        book_path, trade_path = _bundle_paths(config, start, end)
        prior_book_count = len(books)
        _collect_bundle(book_path, "book", config, start, end, books, missing)
        if len(books) > prior_book_count and books[-1].rows == 0:
            empty_books.append((start, end))
        if trade_path is not None:
            prior_trade_count = len(trades)
            _collect_bundle(trade_path, "trade", config, start, end, trades, missing)
            if len(trades) > prior_trade_count and trades[-1].rows == 0:
                empty_trades.append((start, end))
    expected = (1 if config.book_only else 2) * len(windows)
    return OxaArchiveAuditReport(
        symbol=config.symbol,
        market_family=config.market_family,
        requested_start_utc=config.start.isoformat(),
        requested_end_utc=config.end.isoformat(),
        chunk_seconds=int(config.chunk.total_seconds()),
        book_only=config.book_only,
        complete=not missing,
        expected_bundles=expected,
        present_bundles=expected - len(missing),
        missing_directories=tuple(missing),
        book_snapshots=sum(item.rows for item in books),
        public_trades=sum(item.rows for item in trades),
        raw_participant_fills=sum(item.raw_fills for item in trades),
        coalesced_book_snapshots=sum(item.coalesced for item in books),
        censored_zero_size_book_snapshots=sum(
            item.censored_zero_size for item in books
        ),
        empty_book_windows=sum(item.rows == 0 for item in books),
        empty_trade_windows=sum(item.rows == 0 for item in trades),
        empty_book_ranges_utc=_coalesced_utc_ranges(empty_books),
        empty_trade_ranges_utc=_coalesced_utc_ranges(empty_trades),
        evidence_bytes=sum(item.evidence_bytes for item in books + trades),
    )


def _coalesced_utc_ranges(
    windows: list[tuple[datetime, datetime]],
) -> tuple[tuple[str, str], ...]:
    """Coalesce adjacent empty evidence windows into explicit UTC ranges."""
    ranges: list[tuple[datetime, datetime]] = []
    for start, end in windows:
        if ranges and ranges[-1][1] == start:
            ranges[-1] = (ranges[-1][0], end)
        else:
            ranges.append((start, end))
    return tuple((start.isoformat(), end.isoformat()) for start, end in ranges)


def verified_archive_bundles(
    config: OxaArchiveAuditConfig,
) -> tuple[OxaArchiveBundle, ...]:
    """Return chronological replay paths after identity and checksum validation."""
    bundles: list[OxaArchiveBundle] = []
    for evidence in iter_archive_bundle_evidence(config):
        evidence.verify_files()
        bundles.append(evidence.bundle)
    return tuple(bundles)


def iter_archive_bundle_evidence(
    config: OxaArchiveAuditConfig,
) -> Iterator[OxaArchiveBundleEvidence]:
    """Yield identity-validated windows in order without hashing evidence files.

    Every manifest is still read, digested and checked for completeness,
    source, symbol, window, normalization, family, counts and normalized-path
    resolution. Callers must call ``verify_files`` before trusting file bytes.
    """
    for start, end in _iter_windows(config):
        book_dir, trade_dir = _bundle_paths(config, start, end)
        book, book_sha = _identified_manifest(book_dir, "book", config, start, end)
        book_stats = _bundle_stats(book, "book", book_dir)
        trade: dict[str, object] | None = None
        trade_sha: str | None = None
        trade_stats = _BundleStats(0, 0, 0, 0, 0)
        if trade_dir is not None:
            trade, trade_sha = _identified_manifest(
                trade_dir, "trade", config, start, end
            )
            trade_stats = _bundle_stats(trade, "trade", trade_dir)
        bundle = OxaArchiveBundle(
            start=start,
            end=end,
            book_path=_normalized_path(book_dir, book, "books", book_stats.rows),
            trade_path=_normalized_path(
                trade_dir, trade or {}, "trades", trade_stats.rows
            ),
            book_rows=book_stats.rows,
            trade_rows=trade_stats.rows,
        )
        yield OxaArchiveBundleEvidence(
            bundle, book_dir, trade_dir, book, trade, book_sha, trade_sha
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
) -> tuple[Path, Path | None]:
    book = OxaBookRequest(
        config.symbol,
        start,
        end,
        config.depth,
        1000,
        DEFAULT_BOOK_MAX_PAGES,
        30.0,
        market_family=config.market_family,
    )
    if config.book_only:
        return output_directory(config.data_root, book), None
    trade = OxaTradeRequest(
        config.symbol,
        start,
        end,
        1000,
        DEFAULT_TRADE_MAX_PAGES,
        30.0,
        market_family=config.market_family,
    )
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
    manifest = _verified_manifest(directory, kind, config, start, end)
    output.append(_bundle_stats(manifest, kind, directory))


def _verified_manifest(
    directory: Path,
    kind: str,
    config: OxaArchiveAuditConfig,
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    manifest, _digest = _identified_manifest(directory, kind, config, start, end)
    verify_file_evidence(directory, manifest.get("files"))
    return manifest


def _identified_manifest(
    directory: Path,
    kind: str,
    config: OxaArchiveAuditConfig,
    start: datetime,
    end: datetime,
) -> tuple[dict[str, object], str]:
    """Read one manifest once, digest those bytes, and validate its identity."""
    if not directory.is_dir():
        raise FileNotFoundError(f"archive bundle directory is missing: {directory}")
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"archive bundle has no manifest: {directory}")
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw.decode("utf-8"))
    _validate_identity(manifest, kind, config, start, end, directory)
    return manifest, hashlib.sha256(raw).hexdigest()


def _normalized_path(
    directory: Path | None,
    manifest: dict[str, object],
    stem: str,
    rows: int,
) -> Path | None:
    if rows == 0:
        return None
    if directory is None:
        raise ValueError("non-empty archive evidence has no directory")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError(f"archive manifest has invalid file evidence: {directory}")
    candidates = [
        name for name in (f"{stem}.jsonl.gz", f"{stem}.jsonl") if name in files
    ]
    if len(candidates) != 1:
        raise ValueError(
            f"archive manifest has ambiguous normalized evidence: {directory}"
        )
    path = directory / candidates[0]
    return path


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
    if manifest.get("complete") is not True:
        raise ValueError(
            f"archive {kind} bundle is incomplete "
            f"(max_pages={manifest.get('max_pages')!r}, "
            f"continuation_cursor={manifest.get('continuation_cursor')!r}): "
            f"{directory}; move it aside and refetch the window"
        )
    expected_source = _expected_source(kind, config.market_family)
    expected = {
        "complete": True,
        "source": expected_source,
        "symbol": config.symbol,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError(f"archive manifest identity mismatch: {directory}")
    if (
        kind == "trade"
        and manifest.get("normalization_version") != TRADE_NORMALIZATION_VERSION
    ):
        raise ValueError(f"archive trade normalization is stale: {directory}")
    if kind == "book" and config.market_family == "hip3":
        if manifest.get("market_family") != "hip3":
            raise ValueError(f"archive manifest market family mismatch: {directory}")


def _expected_source(kind: str, market_family: MarketFamily) -> str:
    if kind == "trade":
        return "0xarchive_hyperliquid_public_trades"
    if market_family == "hip3":
        return "0xarchive_hyperliquid_hip3_l2"
    return "0xarchive_hyperliquid_native_l2"


def _bundle_stats(
    manifest: dict[str, object], kind: str, directory: Path
) -> _BundleStats:
    row_key = "row_count" if kind == "book" else "trade_count"
    rows = _count(manifest, row_key, directory)
    raw_fills = _count(manifest, "raw_fill_count", directory) if kind == "trade" else 0
    coalesced = (
        _count(manifest, "coalesced_same_ms", directory) if kind == "book" else 0
    )
    censored = (
        _optional_count(manifest, "censored_zero_size_snapshots", directory)
        if kind == "book"
        else 0
    )
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError(f"archive manifest has invalid file evidence: {directory}")
    byte_count = sum(_evidence_bytes(value, directory) for value in files.values())
    return _BundleStats(rows, raw_fills, coalesced, censored, byte_count)


def _optional_count(manifest: dict[str, object], key: str, directory: Path) -> int:
    if key not in manifest:
        return 0
    return _count(manifest, key, directory)


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
