"""Unit tests for immutable v30 forward-readiness prefix hashing."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


SCRIPT = Path("scripts/v30_live_forward_readiness.py")


def _module() -> object:
    spec = spec_from_file_location("v30_live_forward_readiness_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v30 readiness script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prefix_hash_ignores_later_appended_bytes(tmp_path: Path) -> None:
    """The recorded prefix remains reproducible as the live ledger grows."""
    module = _module()
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_bytes(b"first\n")
    byte_count = ledger.stat().st_size
    expected = module._prefix_sha256(ledger, byte_count)
    with ledger.open("ab") as handle:
        handle.write(b"second\n")

    assert module._prefix_sha256(ledger, byte_count) == expected


def test_prefix_hash_rejects_shortened_ledger(tmp_path: Path) -> None:
    """A non-reproducible source prefix fails explicitly."""
    module = _module()
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_bytes(b"short")

    with pytest.raises(OSError, match="became shorter"):
        module._prefix_sha256(ledger, 100)
