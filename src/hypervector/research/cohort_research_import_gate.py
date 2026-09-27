"""Pending-evidence gate that throttles report-only DuckDB research imports."""

from __future__ import annotations

import io
from pathlib import Path
import re

_FILL_EVENT = re.compile(rb'"event_type"\s*:\s*"fill"')
_SCAN_CHUNK_BYTES = 1024 * 1024
_SCAN_CARRY_BYTES = 64
_TAIL_SCAN_BYTES = 64 * 1024


class ResearchImportGate:
    """Import after a new fill, enough pending ledger bytes, or a maximum age.

    Each import rewrites DuckDB indexes and holds the database lock regardless of
    how few events are pending, so small increments wait. A fill changes the
    portfolio archive, so it is imported at the next check. The maximum age also
    applies with nothing pending: that import inserts no rows, but it re-verifies
    every ledger's append-only prefix and keeps the last-success age a liveness
    signal.
    """

    def __init__(
        self,
        ledger_root: Path,
        *,
        minimum_pending_bytes: int,
        maximum_age_seconds: float,
    ) -> None:
        if (
            isinstance(minimum_pending_bytes, bool)
            or not isinstance(minimum_pending_bytes, int)
            or minimum_pending_bytes < 0
        ):
            raise ValueError(
                "research import minimum pending bytes must be a nonnegative integer"
            )
        if not maximum_age_seconds > 0.0:
            raise ValueError("research import maximum age must be positive")
        self._ledger_root = ledger_root
        self._minimum_pending_bytes = minimum_pending_bytes
        self._maximum_age_seconds = maximum_age_seconds
        self._imported: dict[Path, int] | None = None
        self._imported_at = 0.0
        self._submitted: tuple[float, dict[Path, int] | None] | None = None

    @property
    def deadline(self) -> float:
        """Return when the maximum age makes the next import due."""
        return self._imported_at + self._maximum_age_seconds

    def due(self, now: float) -> bool:
        """Return whether pending ledger evidence justifies an import now."""
        if self._imported is None:
            return True
        if now >= self.deadline:
            return True
        try:
            pending = _pending_ranges(self._imported, _ledger_sizes(self._ledger_root))
            if pending is None:
                return True
            if sum(end - start for _, start, end in pending) >= (
                self._minimum_pending_bytes
            ):
                return True
            return any(_contains_fill(path, start, end) for path, start, end in pending)
        except OSError:
            return True

    def submitted(self, now: float) -> None:
        """Record the complete-record prefix a starting import will cover at minimum.

        The importer skips a trailing partial line, so the baseline stops at the
        last newline; the rest of that line is rescanned for a fill next check.
        """
        try:
            sizes: dict[Path, int] | None = {
                path: _complete_prefix_size(path)
                for path in _ledger_sizes(self._ledger_root)
            }
        except OSError:
            sizes = None
        self._submitted = (now, sizes)

    def completed(self, *, succeeded: bool) -> None:
        """Advance the baseline on success; a failure makes the next check due."""
        submitted, self._submitted = self._submitted, None
        if not succeeded or submitted is None or submitted[1] is None:
            self._imported = None
            return
        self._imported_at, self._imported = submitted


def _ledger_sizes(root: Path) -> dict[Path, int]:
    return {path: path.stat().st_size for path in sorted(root.glob("*.jsonl"))}


def _complete_prefix_size(path: Path) -> int:
    """Return the byte boundary after the latest complete JSONL record."""
    with path.open("rb") as handle:
        cursor = handle.seek(0, io.SEEK_END)
        while cursor > 0:
            start = max(0, cursor - _TAIL_SCAN_BYTES)
            handle.seek(start)
            boundary = handle.read(cursor - start).rfind(b"\n")
            if boundary >= 0:
                return start + boundary + 1
            cursor = start
    return 0


def _pending_ranges(
    imported: dict[Path, int],
    sizes: dict[Path, int],
) -> list[tuple[Path, int, int]] | None:
    """Return appended byte ranges, or None when a ledger shrank or vanished."""
    if not imported.keys() <= sizes.keys():
        return None
    ranges: list[tuple[Path, int, int]] = []
    for path, size in sizes.items():
        start = imported.get(path, 0)
        if size < start:
            return None
        if size > start:
            ranges.append((path, start, size))
    return ranges


def _contains_fill(path: Path, start: int, end: int) -> bool:
    carry = b""
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = end - start
        while remaining > 0:
            chunk = handle.read(min(_SCAN_CHUNK_BYTES, remaining))
            if not chunk:
                return False
            window = carry + chunk
            if _FILL_EVENT.search(window) is not None:
                return True
            carry = window[-_SCAN_CARRY_BYTES:]
            remaining -= len(chunk)
    return False
