"""Stable read-only snapshots of an actively appended decision ledger."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
from typing import BinaryIO

from hypervector.data.oxa_storage import file_evidence
from hypervector.paper.report import load_decision_rows

_REVERSE_SCAN_BYTES = 1024 * 1024
_COMPATIBLE_SCOPE = "compatible_execution_history"


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
    start_offset = _earliest_identity_offset(path, identity)
    evidence_extra = {
        "snapshot_scope": _COMPATIBLE_SCOPE,
        "selected_run_id": _identity_text(identity, "run_id"),
        "selected_profile_id": _identity_text(identity, "profile_id"),
        "selected_profile_fingerprint": _identity_text(identity, "profile_fingerprint"),
        "selected_run_fingerprint": _identity_text(identity, "run_fingerprint"),
    }
    with _loaded_suffix_snapshot(
        path,
        start_offset=start_offset,
        allow_incomplete_tail=allow_incomplete_tail,
        evidence_extra=evidence_extra,
    ) as (rows, evidence):
        rebased, source_start, source_end = _rebase_contiguous_rows(rows)
        evidence.update(
            {
                "source_sequence_start": source_start,
                "source_sequence_end": source_end,
            }
        )
        yield rebased, evidence


@contextmanager
def _loaded_suffix_snapshot(
    path: Path,
    *,
    start_offset: int,
    allow_incomplete_tail: bool,
    evidence_extra: Mapping[str, object],
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
        rows: list[dict[str, object]] = load_decision_rows(snapshot)
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
        evidence.update(evidence_extra)
        yield rows, evidence


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
