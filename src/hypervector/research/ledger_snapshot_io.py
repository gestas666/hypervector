"""Bounded in-memory ledger snapshots with exact disk fallback and provenance."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import tempfile
from typing import BinaryIO

from hypervector.data.oxa_storage import file_evidence
from hypervector.paper.report import load_decision_stream
from hypervector.research.mapped_snapshot_file import MappedSnapshotFile

# A live run appends roughly 0.2 GB/day to its decisions share, so this budget
# keeps about ten days of one run in anonymous pages. The former 128 MiB budget
# re-copied the whole share to scratch disk on every 30 s checkpoint after ~15 h.
SNAPSHOT_MEMORY_BYTES = 2 * 1024 * 1024 * 1024


@contextmanager
def loaded_suffix_snapshot(
    path: Path,
    *,
    start_offset: int,
    allow_incomplete_tail: bool,
    evidence_extra: Mapping[str, object],
    projector: Callable[[Path], ProjectedLedgerRows] | None = None,
    stream_projector: Callable[[Iterator[str]], ProjectedLedgerRows] | None = None,
) -> Iterator[tuple[list[dict[str, object]], dict[str, object]]]:
    """Freeze exact suffix bytes, spilling only snapshots above the memory limit."""
    if projector is not None and stream_projector is not None:
        raise ValueError("path and stream projectors are mutually exclusive")
    storage = (
        tempfile.NamedTemporaryFile(prefix="live-ledger-", suffix=".jsonl", mode="w+b")
        if projector is not None
        else MappedSnapshotFile(SNAPSHOT_MEMORY_BYTES)
    )
    with storage as out:
        observed, stable = _copy_suffix(path, out, start_offset, allow_incomplete_tail)
        rows, projection, evidence = _load_snapshot(
            out, path, projector, stream_projector
        )
        _add_snapshot_facts(
            evidence, observed, stable, start_offset, allow_incomplete_tail, projection
        )
        evidence.update(evidence_extra)
        yield rows, evidence


def _copy_suffix(
    path: Path, out: BinaryIO, start: int, allow_partial: bool
) -> tuple[int, int]:
    with path.open("rb") as source:
        source.seek(start)
        observed, stable = _copy_observed_prefix(source, out)
    if observed != stable:
        if not allow_partial:
            raise ValueError(
                f"live decisions ledger has an incomplete trailing JSONL record: {path}"
            )
        out.truncate(stable)
    out.flush()
    return observed + start, stable + start


def _load_snapshot(
    out: BinaryIO,
    source_path: Path,
    projector: Callable[[Path], ProjectedLedgerRows] | None,
    stream_projector: Callable[[Iterator[str]], ProjectedLedgerRows] | None,
) -> tuple[list[dict[str, object]], ProjectedLedgerRows | None, dict[str, object]]:
    if projector is not None:
        path = Path(out.name)
        projection = projector(path)
        return _rebase_projected_rows(projection), projection, file_evidence(path)
    size = out.seek(0, io.SEEK_END)
    out.seek(0)
    evidence = {"bytes": size, "sha256": hashlib.file_digest(out, "sha256").hexdigest()}
    out.seek(0)
    with io.TextIOWrapper(out, encoding="utf-8") as text:
        lines = (line for line in text)
        if stream_projector is None:
            return (
                load_decision_stream(lines, source_label=str(source_path)),
                None,
                evidence,
            )
        projection = stream_projector(lines)
        return _rebase_projected_rows(projection), projection, evidence


def _add_snapshot_facts(
    evidence: dict[str, object],
    observed: int,
    stable: int,
    start: int,
    allow_partial: bool,
    projection: ProjectedLedgerRows | None,
) -> None:
    if allow_partial or start > 0:
        evidence.update(
            {
                "source_bytes_observed": observed,
                "stable_bytes": stable,
                "dropped_tail_bytes": observed - stable,
                "incomplete_tail_dropped": observed != stable,
            }
        )
    if start > 0:
        evidence["source_start_offset"] = start
    if projection is not None:
        evidence.update(
            {
                "source_sequence_start": projection.source_sequence_start,
                "source_sequence_end": projection.source_sequence_end,
                "projected_record_count": len(projection.rows),
            }
        )


@dataclass(frozen=True)
class ProjectedLedgerRows:
    """Selected source rows plus the complete validated source sequence range."""

    rows: list[dict[str, object]]
    source_sequence_start: int
    source_sequence_end: int


def _rebase_projected_rows(projection: ProjectedLedgerRows) -> list[dict[str, object]]:
    rows = projection.rows
    if not rows:
        raise ValueError("compatible execution projection contains no records")
    source_sequences = [row.get("sequence") for row in rows]
    if not all(
        isinstance(value, int) and not isinstance(value, bool)
        for value in source_sequences
    ):
        raise ValueError("compatible execution projection has invalid sequence")
    if source_sequences != sorted(set(source_sequences)):
        raise ValueError("compatible execution projection is not source ordered")
    if (
        source_sequences[0] < projection.source_sequence_start
        or source_sequences[-1] > projection.source_sequence_end
    ):
        raise ValueError("compatible execution projection exceeds source range")
    return [{**row, "sequence": index} for index, row in enumerate(rows, 1)]


def _copy_observed_prefix(source: BinaryIO, target: BinaryIO) -> tuple[int, int]:
    """Copy bytes and return observed length plus last complete-line boundary."""
    observed_bytes = 0
    stable_bytes = 0
    while chunk := source.read(1024 * 1024):
        target.write(chunk)
        last_newline = chunk.rfind(b"\n")
        if last_newline >= 0:
            stable_bytes = observed_bytes + last_newline + 1
        observed_bytes += len(chunk)
    return observed_bytes, stable_bytes
