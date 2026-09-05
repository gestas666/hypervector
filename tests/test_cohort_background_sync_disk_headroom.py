"""Disk-headroom safety tests for report-only cohort research synchronization."""

from __future__ import annotations

from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from hypervector.research.cohort_background_sync import (
    BackgroundResearchSync,
    ResearchSyncError,
)


def test_background_sync_default_runs_with_eleven_gibibytes_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bounded projection may run while preserving an eight GiB reserve."""
    calls: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        "hypervector.research.cohort_background_sync.shutil.disk_usage",
        lambda _path: SimpleNamespace(free=11 * 1024**3),
    )
    controller = BackgroundResearchSync(
        tmp_path / "market.duckdb",
        tmp_path / "ledgers",
        120.0,
        lambda database, ledger: calls.append((database, ledger)) or {},
    )

    controller.poll(now=0.0)
    controller.wait_for_completion(timeout=2.0)
    controller.poll(now=1.0)

    assert calls == [(tmp_path / "market.duckdb", tmp_path / "ledgers")]
    assert controller.pop_error() is None
    controller.close()


def test_background_sync_default_defers_below_eight_gibibytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production default must fail closed below eight GiB free."""
    calls: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        "hypervector.research.cohort_background_sync.shutil.disk_usage",
        lambda _path: SimpleNamespace(free=8 * 1024**3 - 1),
    )
    controller = BackgroundResearchSync(
        tmp_path / "market.duckdb",
        tmp_path / "ledgers",
        120.0,
        lambda database, ledger: calls.append((database, ledger)) or {},
    )

    controller.poll(now=0.0)

    assert calls == []
    assert controller.pop_error() == (
        "research sync deferred: available disk space is below the "
        f"required {8 * 1024**3} bytes"
    )
    controller.close()


def test_background_sync_defers_before_spawning_without_disk_headroom(
    tmp_path: Path,
) -> None:
    """A disk-starved checkpoint must preserve its cache and skip DuckDB work."""
    calls: list[tuple[Path, Path]] = []

    def sync(database: Path, ledger: Path) -> dict[str, object]:
        calls.append((database, ledger))
        return {"imported_events": 1}

    available = shutil.disk_usage(tmp_path).free
    controller = BackgroundResearchSync(
        tmp_path / "market.duckdb",
        tmp_path / "ledgers",
        120.0,
        sync,
        minimum_free_bytes=available + 1,
        portfolio_archive={"cached": True},
    )

    controller.poll(now=0.0)

    assert calls == []
    assert controller.portfolio_archive == {"cached": True}
    assert controller.pop_error() == (
        "research sync deferred: available disk space is below the "
        f"required {available + 1} bytes"
    )
    controller.close()


def test_background_sync_still_runs_with_sufficient_disk_headroom(
    tmp_path: Path,
) -> None:
    """The headroom guard must not change normal background synchronization."""
    calls: list[tuple[Path, Path]] = []

    def sync(database: Path, ledger: Path) -> dict[str, object]:
        calls.append((database, ledger))
        return {"imported_events": 1}

    database = tmp_path / "market.duckdb"
    ledger = tmp_path / "ledgers"
    controller = BackgroundResearchSync(
        database,
        ledger,
        120.0,
        sync,
        minimum_free_bytes=0,
    )

    controller.poll(now=0.0)
    controller.wait_for_completion(timeout=2.0)
    controller.poll(now=1.0)

    assert calls == [(database, ledger)]
    assert controller.pop_report() == {"imported_events": 1}
    assert controller.pop_error() is None
    controller.close()


def test_background_sync_backs_off_after_worker_failure(tmp_path: Path) -> None:
    """A failed slow import must not immediately consume another worker slot."""
    calls: list[tuple[Path, Path]] = []

    def sync(database: Path, ledger: Path) -> dict[str, object]:
        calls.append((database, ledger))
        raise ResearchSyncError("bounded import timed out")

    controller = BackgroundResearchSync(
        tmp_path / "market.duckdb",
        tmp_path / "ledgers",
        120.0,
        sync,
        minimum_free_bytes=0,
    )

    controller.poll(now=0.0)
    with pytest.raises(ResearchSyncError, match="bounded import timed out"):
        controller.wait_for_completion(timeout=2.0)
    controller.poll(now=300.0)
    controller.wait_for_completion(timeout=0.1)

    assert len(calls) == 1
    assert controller.pop_error() == "bounded import timed out"

    controller.poll(now=419.0)
    assert len(calls) == 1
    controller.poll(now=420.0)
    with pytest.raises(ResearchSyncError, match="bounded import timed out"):
        controller.wait_for_completion(timeout=2.0)
    assert len(calls) == 2
    controller.close()
