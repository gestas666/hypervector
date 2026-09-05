"""Exact complete-prefix reading from previously authenticated JSONL bytes."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from hypervector.data.jsonl_prefix import read_jsonl_verified_prefix


def test_verified_prefix_uses_only_the_authenticated_complete_bytes(
    tmp_path: Path,
) -> None:
    """Later rows and an incomplete tail cannot enter an earlier checkpoint."""
    source = tmp_path / "events.jsonl"
    prefix = _line({"sequence": 1}) + _line({"sequence": 2})
    source.write_bytes(prefix + _line({"sequence": 3}) + b'{"sequence":')

    rows = read_jsonl_verified_prefix(
        source,
        "checkpoint ledger",
        length=len(prefix),
        expected_sha256=sha256(prefix).hexdigest(),
    )

    assert rows == ({"sequence": 1}, {"sequence": 2})


def test_verified_prefix_rejects_changed_authenticated_bytes(tmp_path: Path) -> None:
    """A rewritten checkpoint prefix must fail instead of changing history."""
    source = tmp_path / "events.jsonl"
    original = _line({"sequence": 1})
    source.write_bytes(_line({"sequence": 9}))

    with pytest.raises(ValueError, match="hash does not match"):
        read_jsonl_verified_prefix(
            source,
            "checkpoint ledger",
            length=len(original),
            expected_sha256=sha256(original).hexdigest(),
        )


def _line(payload: dict[str, int]) -> bytes:
    return json.dumps(payload, sort_keys=True).encode() + b"\n"
