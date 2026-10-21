"""Discovery tests for retired cohort asset ledgers."""

from __future__ import annotations

from pathlib import Path

from hypervector.research.cohort_historical_asset_ledgers import (
    retired_asset_paths,
)


def test_retired_asset_paths_exclude_cohort_and_active_ledgers(tmp_path: Path) -> None:
    """All-time history should add DDD without duplicating active assets."""
    cohort = _touch(tmp_path / "decisions.jsonl")
    _touch(tmp_path / "btc.jsonl")
    _touch(tmp_path / "xyz:aaa.jsonl")
    ddd = _touch(tmp_path / "xyz:ddd.jsonl")

    paths = retired_asset_paths(
        tmp_path,
        cohort,
        active_symbols=("BTC", "xyz:AAA"),
    )

    assert paths == {"xyz:DDD": ddd}


def _touch(path: Path) -> Path:
    """Create one fixture ledger path."""
    path.touch()
    return path
