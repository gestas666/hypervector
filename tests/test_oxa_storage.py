"""Tests for atomic 0xArchive evidence storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.data.oxa_storage import publish_immutable_directory


def test_failed_bundle_writer_removes_private_staging_directory(
    tmp_path: Path,
) -> None:
    """A failed publication must leave neither success nor hidden debris."""
    final = tmp_path / "bundle"

    def fail(staging: Path) -> None:
        (staging / "partial").write_text("incomplete", encoding="utf-8")
        raise RuntimeError("writer failed")

    with pytest.raises(RuntimeError, match="writer failed"):
        publish_immutable_directory(final, fail)

    assert not final.exists()
    assert list(tmp_path.iterdir()) == []
