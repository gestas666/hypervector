"""Single-backend runtime locking for one Hypervelocity data root."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.runtime_lock import hypervelocity_runtime_lock


def test_second_backend_for_same_root_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "ops"

    with hypervelocity_runtime_lock(root):
        with pytest.raises(RuntimeError, match="already running"):
            with hypervelocity_runtime_lock(root):
                pytest.fail("second backend acquired the same lock")


def test_lock_is_released_after_backend_stops(tmp_path: Path) -> None:
    root = tmp_path / "ops"

    with hypervelocity_runtime_lock(root):
        pass
    with hypervelocity_runtime_lock(root):
        pass
