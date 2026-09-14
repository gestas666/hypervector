"""Authenticate original archive depth before supplying modeled native execution.

Exchange timestamps do not establish historical receive times or queue priority.
Callers must declare the execution-arrival clock, sampling delay and asset lot grid.
"""

import json
from bisect import bisect_left
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    verified_archive_bundles,
)
from hypervector.data.oxa_history import (
    OxaBookPage,
    OxaBookRequest,
    OxaBookSnapshot,
    _merge_page_snapshots,
    _parse_page,
    output_directory,
)
from hypervector.data.oxa_storage import file_evidence, open_text_reader
from hypervector.research.native_replay_depth import ExactLevel, RecordedBook
from hypervector.research.native_replay_events import require_clock


class RecordedBookUnavailable(ValueError):
    """No authenticated snapshot supplies execution within the declared sampling window."""


@dataclass(frozen=True)
class AuthenticatedBookBundle:
    """Retain exact original snapshots and their checksum-bound bundle identity."""

    directory: Path
    manifest_sha256: str
    snapshots: tuple[OxaBookSnapshot, ...]

    def execution_book(
        self, arrival_ms: int, *, maximum_delay_ms: int, quantity_step: Decimal
    ) -> RecordedBook:
        """Select an exchange snapshot; separate retrievals cannot replenish its liquidity."""
        require_clock(arrival_ms, "execution arrival")
        require_clock(maximum_delay_ms, "maximum execution sampling delay")
        index = bisect_left(self.snapshots, arrival_ms, key=lambda row: row.ts_exchange_ms)
        if index == len(self.snapshots):
            raise RecordedBookUnavailable(f"no book at/after {arrival_ms}: {self.directory}")
        row = self.snapshots[index]
        if row.ts_exchange_ms - arrival_ms > maximum_delay_ms:
            raise RecordedBookUnavailable(
                f"book exceeds sampling delay at {arrival_ms}: {self.directory}"
            )
        return RecordedBook(
            f"0xarchive:{row.symbol}:{row.ts_exchange_ms}",
            row.symbol,
            row.ts_exchange_ms,
            quantity_step,
            tuple(ExactLevel(Decimal(level.px), Decimal(level.sz)) for level in row.bids),
            tuple(ExactLevel(Decimal(level.px), Decimal(level.sz)) for level in row.asks),
        )


def authenticate_book_bundle(data_root: Path, request: OxaBookRequest) -> AuthenticatedBookBundle:
    """Verify file checksums, raw-page completion and exact raw-to-normalized agreement."""
    directory = output_directory(data_root, request)
    config = OxaArchiveAuditConfig(
        request.symbol,
        request.start,
        request.end,
        data_root,
        chunk=request.end - request.start,
        depth=request.depth,
        market_family=request.market_family,
        book_only=True,
    )
    verified_archive_bundles(config)
    manifest_path = directory / "manifest.json"
    manifest = _mapping(json.loads(manifest_path.read_text()), "manifest")
    files = _mapping(manifest.get("files"), "manifest files")
    pages = _raw_pages(directory, manifest, files, request)
    snapshots, coalesced = _merge_page_snapshots(pages)
    _validate_metadata(manifest, request, pages, snapshots, coalesced)
    _validate_normalized(directory, files, request, pages, snapshots)
    checksum = file_evidence(manifest_path)["sha256"]
    if not isinstance(checksum, str):
        raise ValueError("manifest checksum must be a string")
    return AuthenticatedBookBundle(directory, checksum, snapshots)


def _raw_pages(
    directory: Path, manifest: dict[str, object], files: dict[str, object], request: OxaBookRequest
) -> list[OxaBookPage]:
    count = _count(manifest.get("page_count"), "page count")
    if not 1 <= count <= request.max_pages:
        raise ValueError(f"archive page count exceeds explicit reader bounds: {directory}")
    selected = []
    for index in range(1, count + 1):
        choices = [f"raw/page-{index:04d}.json{suffix}" for suffix in ("", ".gz")]
        names = [name for name in choices if name in files]
        if len(names) != 1:
            raise ValueError(f"missing or ambiguous original page {index}: {directory}")
        selected.append(names[0])
    if set(selected) != {name for name in files if name.startswith("raw/")}:
        raise ValueError(f"unaccounted original archive pages: {directory}")
    pages = []
    for name in selected:
        with open_text_reader(directory / name) as handle:
            pages.append(_parse_page(json.load(handle), request))
    if pages[-1].next_cursor is not None or any(page.next_cursor is None for page in pages[:-1]):
        raise ValueError(f"original archive pages do not prove complete pagination: {directory}")
    return pages


def _validate_metadata(
    manifest: dict[str, object],
    request: OxaBookRequest,
    pages: list[OxaBookPage],
    snapshots: tuple[OxaBookSnapshot, ...],
    coalesced: int,
) -> None:
    expected = {
        "requested_depth": request.depth,
        "continuation_cursor": None,
        "request_ids": [page.request_id for page in pages],
        "observed_start": snapshots[0].timestamp if snapshots else None,
        "observed_end": snapshots[-1].timestamp if snapshots else None,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("archive metadata disagrees with original page identity or bounds")
    counts = {
        "row_count": len(snapshots),
        "coalesced_same_ms": coalesced,
        "censored_zero_size_snapshots": sum(page.censored_zero_size_snapshots for page in pages),
    }
    for key, value in counts.items():
        observed = (
            manifest.get(key, 0) if key == "censored_zero_size_snapshots" else manifest.get(key)
        )
        if _count(observed, key) != value:
            raise ValueError(f"archive {key} disagrees with original pages")


def _validate_normalized(
    directory: Path,
    files: dict[str, object],
    request: OxaBookRequest,
    pages: list[OxaBookPage],
    snapshots: tuple[OxaBookSnapshot, ...],
) -> None:
    choices = [name for name in ("books.jsonl", "books.jsonl.gz") if name in files]
    if len(choices) != 1:
        raise ValueError(f"archive requires exactly one normalized book stream: {directory}")
    request_ids = {row.ts_exchange_ms: page.request_id for page in pages for row in page.snapshots}
    with open_text_reader(directory / choices[0]) as handle:
        for index, row in enumerate(snapshots, 1):
            line = handle.readline()
            expected = row.to_replay_row(
                request_id=request_ids[row.ts_exchange_ms], source=request.source
            )
            if not line or json.loads(line) != expected:
                raise ValueError(
                    f"normalized book {index} disagrees with original response: {directory}"
                )
        if handle.readline():
            raise ValueError(f"normalized archive contains unexplained extra books: {directory}")


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"archive {label} must be an object with string keys")
    return value


def _count(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"archive {label} must be a nonnegative integer")
    return value
