"""Exact dependency provenance for long-running HIP-3 diagnostics."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.research.hip3_development_provenance import (
    require_unchanged_dependencies,
    require_unchanged_file,
    source_dependency_identity,
)
from hypervector.data.oxa_storage import file_evidence


def test_unrelated_file_change_does_not_invalidate_exact_dependencies(
    tmp_path: Path,
) -> None:
    dependency = tmp_path / "dependency.py"
    unrelated = tmp_path / "unrelated.py"
    dependency.write_text("VALUE = 1\n", encoding="utf-8")
    unrelated.write_text("VALUE = 1\n", encoding="utf-8")
    identity = source_dependency_identity(tmp_path, (dependency,))

    unrelated.write_text("VALUE = 2\n", encoding="utf-8")

    require_unchanged_dependencies(identity, tmp_path)


def test_dependency_change_fails_closed(tmp_path: Path) -> None:
    dependency = tmp_path / "dependency.py"
    dependency.write_text("VALUE = 1\n", encoding="utf-8")
    identity = source_dependency_identity(tmp_path, (dependency,))

    dependency.write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="dependency source changed"):
        require_unchanged_dependencies(identity, tmp_path)


def test_dependency_identity_rejects_paths_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.py"
    outside.write_text("VALUE = 1\n", encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="outside project root"):
            source_dependency_identity(tmp_path, (outside,))
    finally:
        outside.unlink(missing_ok=True)


def test_path_decorated_file_reference_compares_only_hash_and_bytes(
    tmp_path: Path,
) -> None:
    database = tmp_path / "research.duckdb"
    database.write_bytes(b"stable database bytes")
    expected = {"path": str(database.resolve()), **file_evidence(database)}

    require_unchanged_file(database, expected)

    database.write_bytes(b"changed database bytes")
    with pytest.raises(ValueError, match="changed during evaluation"):
        require_unchanged_file(database, expected)
