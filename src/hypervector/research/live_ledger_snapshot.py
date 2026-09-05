"""Stable read-only snapshots of an actively appended decision ledger."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tempfile
from typing import BinaryIO

from hypervector.data.oxa_storage import file_evidence
from hypervector.paper.report import load_decision_rows

_REVERSE_SCAN_BYTES = 1024 * 1024
_COMPATIBLE_SCOPE = "compatible_execution_history"
_CURRENT_RUN_SCOPE = "current_run"


@dataclass(frozen=True)
class _CompatibleExecutionBoundary:
    path: Path
    identity: tuple[str, str, str]
    start_offset: int
    start_line_sha256: str
    source_device: int
    source_inode: int
    observed_bytes: int


@dataclass(frozen=True)
class ProjectedLedgerRows:
    """Selected source rows plus the complete validated source sequence range."""

    rows: list[dict[str, object]]
    source_sequence_start: int
    source_sequence_end: int


_COMPATIBLE_BOUNDARIES: dict[
    tuple[Path, tuple[str, str, str]], _CompatibleExecutionBoundary
] = {}


@contextmanager
def snapshot_decision_ledger(
    path: Path,
    *,
    allow_incomplete_tail: bool = False,
    run_id: str | None = None,
    latest_armed_run: bool = False,
) -> Iterator[tuple[list[dict[str, object]], dict[str, object]]]:
    """Copy and load a complete JSONL prefix without mutating its source."""
    if not path.is_file():
        raise FileNotFoundError(f"live decisions ledger does not exist: {path}")
    start_offset, selected_run_id = _snapshot_start(path, run_id, latest_armed_run)
    extra = {"selected_run_id": selected_run_id} if selected_run_id is not None else {}
    with _loaded_suffix_snapshot(
        path,
        start_offset=start_offset,
        allow_incomplete_tail=allow_incomplete_tail,
        evidence_extra=extra,
    ) as result:
        yield result


@contextmanager
def snapshot_current_run_ledger(
    path: Path,
    *,
    run_id: str,
    allow_incomplete_tail: bool = False,
) -> Iterator[tuple[list[dict[str, object]], dict[str, object]]]:
    """Load and rebase only the exact requested run's ledger suffix."""
    with snapshot_decision_ledger(
        path,
        allow_incomplete_tail=allow_incomplete_tail,
        run_id=run_id,
    ) as (rows, evidence):
        rebased, source_start, source_end = _rebase_contiguous_rows(rows)
        evidence.update(
            {
                "snapshot_scope": _CURRENT_RUN_SCOPE,
                "source_sequence_start": source_start,
                "source_sequence_end": source_end,
            }
        )
        yield rebased, evidence


@contextmanager
def snapshot_compatible_execution_ledger(
    path: Path,
    *,
    run_id: str,
    allow_incomplete_tail: bool = False,
) -> Iterator[tuple[list[dict[str, object]], dict[str, object]]]:
    """Load and rebase history from the earliest matching execution identity."""
    if not path.is_file():
        raise FileNotFoundError(f"live decisions ledger does not exist: {path}")
    identity = _selected_execution_identity(path, run_id)
    boundary, cache_hit = _compatible_execution_boundary(path, identity)
    evidence_extra = {
        "snapshot_scope": _COMPATIBLE_SCOPE,
        "selected_run_id": _identity_text(identity, "run_id"),
        "selected_profile_id": _identity_text(identity, "profile_id"),
        "selected_profile_fingerprint": _identity_text(identity, "profile_fingerprint"),
        "selected_run_fingerprint": _identity_text(identity, "run_fingerprint"),
        "source_start_offset_cache_hit": cache_hit,
        "source_start_line_sha256": boundary.start_line_sha256,
        "source_device": boundary.source_device,
        "source_inode": boundary.source_inode,
    }
    with _loaded_suffix_snapshot(
        path,
        start_offset=boundary.start_offset,
        allow_incomplete_tail=allow_incomplete_tail,
        evidence_extra=evidence_extra,
    ) as (rows, evidence):
        _advance_compatible_boundary(boundary, evidence)
        rebased, source_start, source_end = _rebase_contiguous_rows(rows)
        evidence.update(
            {
                "source_sequence_start": source_start,
                "source_sequence_end": source_end,
            }
        )
        yield rebased, evidence


@contextmanager
def snapshot_projected_compatible_execution_ledger(
    path: Path,
    *,
    run_id: str,
    projector: Callable[[Path], ProjectedLedgerRows],
    allow_incomplete_tail: bool = False,
) -> Iterator[tuple[list[dict[str, object]], dict[str, object]]]:
    """Stream-project a stable compatible suffix without materializing all rows."""
    if not path.is_file():
        raise FileNotFoundError(f"live decisions ledger does not exist: {path}")
    identity = _selected_execution_identity(path, run_id)
    boundary, cache_hit = _compatible_execution_boundary(path, identity)
    evidence_extra = {
        "snapshot_scope": _COMPATIBLE_SCOPE,
        "selected_run_id": _identity_text(identity, "run_id"),
        "selected_profile_id": _identity_text(identity, "profile_id"),
        "selected_profile_fingerprint": _identity_text(identity, "profile_fingerprint"),
        "selected_run_fingerprint": _identity_text(identity, "run_fingerprint"),
        "source_start_offset_cache_hit": cache_hit,
        "source_start_line_sha256": boundary.start_line_sha256,
        "source_device": boundary.source_device,
        "source_inode": boundary.source_inode,
    }
    with _loaded_suffix_snapshot(
        path,
        start_offset=boundary.start_offset,
        allow_incomplete_tail=allow_incomplete_tail,
        evidence_extra=evidence_extra,
        projector=projector,
    ) as (rows, evidence):
        _advance_compatible_boundary(boundary, evidence)
        yield rows, evidence


def _compatible_execution_boundary(
    path: Path,
    selected: Mapping[str, object],
) -> tuple[_CompatibleExecutionBoundary, bool]:
    resolved = path.resolve()
    identity = _execution_identity(selected)
    key = (resolved, identity)
    cached = _COMPATIBLE_BOUNDARIES.get(key)
    if cached is not None:
        _validate_compatible_boundary(cached)
        return cached, True
    start_offset = _earliest_identity_offset(path, selected)
    source = path.stat()
    raw = _boundary_line(path, start_offset)
    boundary = _CompatibleExecutionBoundary(
        resolved,
        identity,
        start_offset,
        hashlib.sha256(raw).hexdigest(),
        source.st_dev,
        source.st_ino,
        source.st_size,
    )
    _COMPATIBLE_BOUNDARIES[key] = boundary
    return boundary, False


def _validate_compatible_boundary(boundary: _CompatibleExecutionBoundary) -> None:
    source = boundary.path.stat()
    if (
        source.st_dev != boundary.source_device
        or source.st_ino != boundary.source_inode
    ):
        raise ValueError("compatible execution ledger identity changed after caching")
    if source.st_size < boundary.observed_bytes:
        raise ValueError("compatible execution ledger was truncated after caching")
    raw = _boundary_line(boundary.path, boundary.start_offset)
    if hashlib.sha256(raw).hexdigest() != boundary.start_line_sha256:
        raise ValueError("compatible execution boundary changed after caching")
    row = _configuration_identity(raw)
    if row is None or _execution_identity(row) != boundary.identity:
        raise ValueError("compatible execution boundary identity changed after caching")


def _advance_compatible_boundary(
    boundary: _CompatibleExecutionBoundary,
    evidence: Mapping[str, object],
) -> None:
    observed = evidence.get("source_bytes_observed", evidence.get("bytes"))
    if isinstance(observed, bool) or not isinstance(observed, int):
        raise ValueError("compatible execution snapshot omitted observed bytes")
    key = (boundary.path, boundary.identity)
    _COMPATIBLE_BOUNDARIES[key] = _CompatibleExecutionBoundary(
        boundary.path,
        boundary.identity,
        boundary.start_offset,
        boundary.start_line_sha256,
        boundary.source_device,
        boundary.source_inode,
        observed,
    )


def _boundary_line(path: Path, offset: int) -> bytes:
    with path.open("rb") as handle:
        handle.seek(offset)
        raw = handle.readline()
    if not raw.endswith(b"\n"):
        raise ValueError("compatible execution boundary is not a complete row")
    return raw


@contextmanager
def _loaded_suffix_snapshot(
    path: Path,
    *,
    start_offset: int,
    allow_incomplete_tail: bool,
    evidence_extra: Mapping[str, object],
    projector: Callable[[Path], ProjectedLedgerRows] | None = None,
) -> Iterator[tuple[list[dict[str, object]], dict[str, object]]]:
    with tempfile.NamedTemporaryFile(
        prefix="live-ledger-",
        suffix=".jsonl",
        mode="w+b",
    ) as out:
        with path.open("rb") as source:
            source.seek(start_offset)
            suffix_bytes, suffix_stable_bytes = _copy_observed_prefix(source, out)
        observed_bytes = start_offset + suffix_bytes
        stable_bytes = start_offset + suffix_stable_bytes
        dropped_bytes = observed_bytes - stable_bytes
        if dropped_bytes and not allow_incomplete_tail:
            raise ValueError(
                f"live decisions ledger has an incomplete trailing JSONL record: {path}"
            )
        if dropped_bytes:
            out.truncate(suffix_stable_bytes)
        out.flush()
        snapshot = Path(out.name)
        projection = None if projector is None else projector(snapshot)
        rows = (
            load_decision_rows(snapshot)
            if projection is None
            else _rebase_projected_rows(projection)
        )
        evidence = file_evidence(snapshot)
        if allow_incomplete_tail or start_offset > 0:
            evidence.update(
                {
                    "source_bytes_observed": observed_bytes,
                    "stable_bytes": stable_bytes,
                    "dropped_tail_bytes": dropped_bytes,
                    "incomplete_tail_dropped": dropped_bytes > 0,
                }
            )
        if start_offset > 0:
            evidence["source_start_offset"] = start_offset
        if projection is not None:
            evidence.update(
                {
                    "source_sequence_start": projection.source_sequence_start,
                    "source_sequence_end": projection.source_sequence_end,
                    "projected_record_count": len(rows),
                }
            )
        evidence.update(evidence_extra)
        yield rows, evidence


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


def latest_decision_ledger_event(path: Path, event_type: str) -> dict[str, object]:
    """Return the newest complete event of one exact type without a full copy."""
    if not path.is_file():
        raise FileNotFoundError(f"live decisions ledger does not exist: {path}")
    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("ledger event type must be non-empty text")
    for _, raw in _reverse_complete_lines(path):
        if event_type.encode("utf-8") not in raw:
            continue
        value: object = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("live decision ledger event must be an object")
        if value.get("event_type") == event_type:
            return value
    raise ValueError(f"live decisions ledger has no {event_type} event: {path}")


def _selected_execution_identity(
    path: Path,
    requested_run_id: str,
) -> Mapping[str, object]:
    for _, raw in _reverse_complete_lines(path):
        row = _configuration_identity(raw)
        if row is None or row.get("live_armed") is not True:
            continue
        candidate = row.get("run_id")
        if candidate == requested_run_id:
            _execution_identity(row)
            return row
    raise ValueError(f"configuration identity not found for {requested_run_id}: {path}")


def _earliest_identity_offset(path: Path, selected: Mapping[str, object]) -> int:
    target = _execution_identity(selected)
    with path.open("rb") as handle:
        while raw := handle.readline():
            offset = handle.tell() - len(raw)
            row = _configuration_identity(raw)
            if row is not None and _execution_identity(row) == target:
                return offset
    raise ValueError(f"compatible execution identity not found: {path}")


def _execution_identity(row: Mapping[str, object]) -> tuple[str, str, str]:
    return tuple(
        _identity_text(row, key)
        for key in ("profile_id", "profile_fingerprint", "run_fingerprint")
    )  # type: ignore[return-value]


def _identity_text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"live configuration identity requires {key}")
    return value.strip()


def _rebase_contiguous_rows(
    rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], int, int]:
    if not rows:
        raise ValueError("compatible execution snapshot contains no records")
    source_start = rows[0].get("sequence")
    if isinstance(source_start, bool) or not isinstance(source_start, int):
        raise ValueError("compatible execution snapshot has invalid sequence")
    for expected, row in enumerate(rows, source_start):
        if row.get("sequence") != expected:
            raise ValueError(
                f"compatible execution sequence is not contiguous at {expected}"
            )
    return (
        [{**row, "sequence": index} for index, row in enumerate(rows, 1)],
        source_start,
        source_start + len(rows) - 1,
    )


def _snapshot_start(
    path: Path,
    requested_run_id: str | None,
    latest_armed_run: bool,
) -> tuple[int, str | None]:
    if requested_run_id is not None and latest_armed_run:
        raise ValueError("run_id and latest_armed_run are mutually exclusive")
    if requested_run_id is None and not latest_armed_run:
        return 0, None
    for offset, raw in _reverse_complete_lines(path):
        row = _configuration_identity(raw)
        if row is None:
            continue
        candidate = row.get("run_id")
        if not isinstance(candidate, str) or not candidate:
            continue
        if requested_run_id == candidate:
            return offset, candidate
        if latest_armed_run and row.get("live_armed") is True:
            return offset, candidate
    target = requested_run_id or "latest armed run"
    raise ValueError(f"configuration identity not found for {target}: {path}")


def _configuration_identity(raw: bytes) -> Mapping[str, object] | None:
    if b"configuration_identity" not in raw:
        return None
    value = json.loads(raw)
    if not isinstance(value, Mapping):
        raise ValueError("live configuration identity must be an object")
    return value if value.get("event_type") == "configuration_identity" else None


def _reverse_complete_lines(path: Path) -> Iterator[tuple[int, bytes]]:
    """Yield complete non-empty lines newest-first with bounded memory."""
    with path.open("rb") as handle:
        cursor = path.stat().st_size
        carry = b""
        while cursor > 0:
            start = max(0, cursor - _REVERSE_SCAN_BYTES)
            handle.seek(start)
            data = handle.read(cursor - start) + carry
            parts = data.split(b"\n")
            if start > 0:
                carry = parts.pop(0)
                offset = start + len(carry) + 1
            else:
                carry = b""
                offset = 0
            located: list[tuple[int, bytes]] = []
            for part in parts:
                if part:
                    located.append((offset, part))
                offset += len(part) + 1
            yield from reversed(located)
            cursor = start


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
