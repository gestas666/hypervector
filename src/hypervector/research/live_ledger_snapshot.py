"""Stable read-only snapshots of an actively appended decision ledger."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path

from hypervector.research.ledger_snapshot_io import (
    ProjectedLedgerRows,
    loaded_suffix_snapshot as _loaded_suffix_snapshot,
)

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
    projector: Callable[[Path], ProjectedLedgerRows] | None = None,
    stream_projector: Callable[[Iterator[str]], ProjectedLedgerRows] | None = None,
    allow_incomplete_tail: bool = False,
) -> Iterator[tuple[list[dict[str, object]], dict[str, object]]]:
    """Project a frozen compatible suffix through one path or stream consumer."""
    if (projector is None) == (stream_projector is None):
        raise ValueError("exactly one path or stream projector is required")
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
        stream_projector=stream_projector,
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


def latest_decision_ledger_event(path: Path, event_type: str) -> dict[str, object]:
    """Return the newest complete event of one exact type without a full copy."""
    if not path.is_file():
        raise FileNotFoundError(f"live decisions ledger does not exist: {path}")
    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("ledger event type must be non-empty text")
    for _offset, raw in _reverse_complete_lines(path):
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
    """Yield complete non-empty lines newest-first with bounded memory.

    A live ledger is appended to while it is read, so its final line may be a
    partial write. Skipping it here keeps the guarantee in one place: every reader
    that shares this generator was otherwise parsing that torn record.
    """
    size = path.stat().st_size
    if not size:
        return
    with path.open("rb") as handle:
        handle.seek(size - 1)
        terminated = handle.read(1) == b"\n"
        cursor = size
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
                if part and (terminated or offset + len(part) < size):
                    located.append((offset, part))
                offset += len(part) + 1
            yield from reversed(located)
            cursor = start


_CONFIGURATION_BOUNDARIES: dict[tuple[Path, str], _CompatibleExecutionBoundary] = {}


def configuration_identity_ancestry(
    path: Path, run_ids: frozenset[str], *, before_offset: int
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Read authenticated prior identity rows without materializing their runs."""
    resolved = path.resolve()
    missing = {
        run for run in run_ids if (resolved, run) not in _CONFIGURATION_BOUNDARIES
    }
    if missing:
        _cache_configuration_boundaries(path, missing, before_offset)
    rows: list[dict[str, object]] = []
    evidence: list[dict[str, object]] = []
    for run in sorted(run_ids):
        boundary = _CONFIGURATION_BOUNDARIES[(resolved, run)]
        if boundary.start_offset >= before_offset:
            raise ValueError(
                f"cohort ancestry identity is not prior to current run: {run}"
            )
        _validate_compatible_boundary(boundary)
        raw = _boundary_line(path, boundary.start_offset)
        row = _ancestry_identity(raw, run)
        rows.append(row)
        _CONFIGURATION_BOUNDARIES[(resolved, run)] = replace(
            boundary, observed_bytes=max(boundary.observed_bytes, path.stat().st_size)
        )
        evidence.append(
            {
                "run_id": run,
                "source_offset": boundary.start_offset,
                "bytes": len(raw),
                "sha256": boundary.start_line_sha256,
                "source_device": boundary.source_device,
                "source_inode": boundary.source_inode,
                "source_sequence": row.get("sequence"),
            }
        )
    return sorted(rows, key=_ancestry_sequence), evidence


def _cache_configuration_boundaries(
    path: Path, missing: set[str], before_offset: int
) -> None:
    source = path.stat()
    for offset, raw in _reverse_complete_lines(path):
        if offset >= before_offset:
            continue
        row = _configuration_identity(raw)
        if row is None or row.get("run_id") not in missing:
            continue
        run = _identity_text(row, "run_id")
        line = _boundary_line(path, offset)
        _CONFIGURATION_BOUNDARIES[(path.resolve(), run)] = _CompatibleExecutionBoundary(
            path.resolve(),
            _execution_identity(row),
            offset,
            hashlib.sha256(line).hexdigest(),
            source.st_dev,
            source.st_ino,
            source.st_size,
        )
        missing.remove(run)
        if not missing:
            return
    raise ValueError(
        f"prior cohort configuration identities missing: {sorted(missing)}"
    )


def _ancestry_identity(raw: bytes, run_id: str) -> dict[str, object]:
    row = _configuration_identity(raw)
    if row is None or row.get("run_id") != run_id:
        raise ValueError(f"cohort ancestry run identity changed: {run_id}")
    _ancestry_sequence(row)
    return dict(row)


def _ancestry_sequence(row: Mapping[str, object]) -> int:
    value = row.get("sequence")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("cohort ancestry source sequence must be a positive integer")
    return value
