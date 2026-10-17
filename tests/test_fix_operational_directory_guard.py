"""Default tests cannot create folders inside the checkout's real paper/live data roots.

Two runtime-assembly tests used to build the operator inbox from a profile's relative
``data/live/bidirectional_cohort`` ledger, creating its queue folders in the checkout.
"""

import os
from pathlib import Path
import uuid

import pytest

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.mark.parametrize("root", ["live", "paper"])
def test_unit_mkdir_inside_operational_data_is_refused(root: str) -> None:
    """Both ``os.mkdir`` and ``Path.mkdir(parents=True)`` stop before touching the disk."""
    target = DATA / root / f"unit-guard-{uuid.uuid4().hex}"
    try:
        with pytest.raises(AssertionError, match="operational trading directories"):
            os.mkdir(target)
        with pytest.raises(AssertionError, match="operational trading directories"):
            (target / "pending").mkdir(parents=True, exist_ok=True)
    finally:
        for leaked in (target / "pending", target):
            if leaked.is_dir():
                leaked.rmdir()
    assert not target.exists()


def test_unit_mkdir_outside_operational_data_is_unchanged(tmp_path: Path) -> None:
    """Temporary ledgers keep working, including the operator inbox's nested folders."""
    queue = tmp_path / "live/bidirectional_cohort/operator_commands/pending"
    queue.mkdir(parents=True)
    os.mkdir(tmp_path / "flat")
    assert queue.is_dir() and (tmp_path / "flat").is_dir()
