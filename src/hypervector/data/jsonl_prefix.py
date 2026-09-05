"""Immutable identities for complete append-only JSONL prefixes."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
from typing import cast

JsonRecord = dict[str, object]


def read_jsonl_prefix(
    path: Path, label: str
) -> tuple[tuple[JsonRecord, ...], dict[str, object]]:
    """Read and hash the latest complete append-only JSONL prefix."""
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    length = _complete_prefix_size(path)
    if length == 0:
        raise ValueError(f"{label} has no complete JSONL rows")
    content = _read_prefix(path, length)
    rows = tuple(
        _json_object(line, label, line_number)
        for line_number, line in enumerate(content.splitlines(), start=1)
    )
    return rows, {
        "path": str(path.resolve()),
        "bytes": length,
        "sha256": hashlib.sha256(content).hexdigest(),
        "rows": len(rows),
    }


def read_jsonl_verified_prefix(
    path: Path,
    label: str,
    *,
    length: int,
    expected_sha256: str,
) -> tuple[JsonRecord, ...]:
    """Read only a previously authenticated complete JSONL prefix."""
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    size = _integer(length, f"{label} prefix bytes")
    if size == 0:
        raise ValueError(f"{label} has no complete JSONL rows")
    if not _valid_sha256(expected_sha256):
        raise ValueError(f"{label} sha256 is invalid")
    content = _read_prefix(path, size)
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError(f"{label} hash does not match authenticated prefix")
    return tuple(
        _json_object(line, label, line_number)
        for line_number, line in enumerate(content.splitlines(), start=1)
    )


def require_jsonl_prefix_unchanged(
    path: Path, evidence: Mapping[str, object], label: str
) -> None:
    """Fail if a consumed JSONL prefix was truncated or rewritten."""
    length = _integer(evidence.get("bytes"), f"{label} prefix bytes")
    content = _read_prefix(path, length)
    if hashlib.sha256(content).hexdigest() != evidence.get("sha256"):
        raise ValueError(f"{label} prefix changed during evaluation: {path}")


def _complete_prefix_size(path: Path) -> int:
    size = path.stat().st_size
    if size == 0:
        return 0
    with path.open("rb") as stream:
        stream.seek(size - 1)
        if stream.read(1) == b"\n":
            return size
        cursor = size
        while cursor > 0:
            start = max(0, cursor - 64 * 1024)
            stream.seek(start)
            block = stream.read(cursor - start)
            boundary = block.rfind(b"\n")
            if boundary >= 0:
                return start + boundary + 1
            cursor = start
    return 0


def _read_prefix(path: Path, length: int) -> bytes:
    with path.open("rb") as stream:
        content = stream.read(length)
    if len(content) != length:
        raise ValueError(f"JSONL prefix changed during read: {path}")
    return content


def _json_object(line: bytes, label: str, line_number: int) -> JsonRecord:
    value = json.loads(line)
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} row {line_number} must be an object")
    return cast(JsonRecord, value)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
