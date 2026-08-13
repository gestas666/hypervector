"""Discovery tests for retired cohort asset ledgers."""

from __future__ import annotations

from pathlib import Path

from hypervector.research.cohort_historical_asset_ledgers import (
    retired_asset_paths,
)


def test_retired_asset_paths_exclude_cohort_and_active_ledgers(tmp_path: Path) -> None:
    """All-time history should add GOLD without duplicating active assets."""
    cohort = _touch(tmp_path / "decisions.jsonl")
    _touch(tmp_path / "btc.jsonl")
    _touch(tmp_path / "xyz:sp500.jsonl")
    gold = _touch(tmp_path / "xyz:gold.jsonl")

    paths = retired_asset_paths(
        tmp_path,
        cohort,
        active_symbols=("BTC", "xyz:SP500"),
    )

    assert paths == {"xyz:GOLD": gold}


def _touch(path: Path) -> Path:
    """Create one fixture ledger path."""
    path.touch()
    return path
