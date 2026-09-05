"""Frozen JSONL prefix loading for the V85 route audit."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path


Record = Mapping[str, object]
JsonObject = dict[str, object]


def load_frozen_jsonl_prefix(evidence: Record) -> tuple[list[JsonObject], JsonObject]:
    """Load, hash, validate, and rebase one frozen JSONL byte range."""
    path = Path(_text(evidence.get("path"), "frozen prefix path"))
    start = _integer(evidence.get("source_start_offset"), "source start offset")
    observed = _integer(evidence.get("source_bytes_observed"), "source bytes observed")
    length = _integer(evidence.get("suffix_bytes"), "suffix bytes")
    expected_hash = _sha256(evidence.get("sha256"), "frozen prefix")
    if observed != start + length:
        raise ValueError("frozen prefix byte boundary is inconsistent")
    source_size = path.stat().st_size
    if source_size < observed:
        raise ValueError("frozen JSONL source is shorter than its evidence boundary")
    with path.open("rb") as handle:
        handle.seek(start)
        content = handle.read(length)
    if len(content) != length:
        raise ValueError("frozen JSONL prefix became shorter during read")
    if hashlib.sha256(content).hexdigest() != expected_hash:
        raise ValueError("frozen JSONL prefix SHA-256 mismatch")
    rows = _decode_complete_rows(content)
    source_start = _integer(
        evidence.get("source_sequence_start"), "source sequence start"
    )
    source_end = _integer(evidence.get("source_sequence_end"), "source sequence end")
    _validate_sequences(rows, source_start, source_end)
    rebased = [{**row, "sequence": index} for index, row in enumerate(rows, 1)]
    facts: JsonObject = dict(evidence)
    facts["rows"] = len(rows)
    facts["appended_bytes_excluded"] = source_size - observed
    facts["prefix_verified"] = True
    return rebased, facts


def _decode_complete_rows(content: bytes) -> list[JsonObject]:
    if not content or not content.endswith(b"\n"):
        raise ValueError("frozen prefix must end with a complete JSONL row")
    rows: list[JsonObject] = []
    for line_number, raw in enumerate(content.splitlines(), 1):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"frozen prefix JSONL row {line_number} is malformed"
            ) from exc
        if not isinstance(value, dict):
            raise ValueError(f"frozen prefix JSONL row {line_number} must be an object")
        rows.append(value)
    return rows


def _validate_sequences(rows: Sequence[Record], start: int, end: int) -> None:
    if not rows or end - start + 1 != len(rows):
        raise ValueError("frozen prefix sequence boundary disagrees with row count")
    for expected, row in enumerate(rows, start):
        if row.get("sequence") != expected:
            raise ValueError(
                f"frozen prefix source sequence is not contiguous at {expected}"
            )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _sha256(value: object, label: str) -> str:
    digest = _text(value, f"{label} SHA-256")
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError(f"{label} SHA-256 must be a lower-case hexadecimal digest")
    return digest
