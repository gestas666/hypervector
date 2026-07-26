"""I2 data layout — ensure_data_layout and path separation."""

from __future__ import annotations

from pathlib import Path

from hypervector.infra import DATA_SUBDIRS, ensure_data_layout, layout_report, paths_for


def test_ensure_data_layout_creates_all_subdirs(tmp_path: Path):
    root = tmp_path / "data"
    paths = ensure_data_layout(root)
    assert paths.root == root
    for rel in DATA_SUBDIRS:
        assert (root / rel).is_dir(), rel
    assert paths.runs_db == root / "runs" / "hypervector.db"
    assert paths.paper_db == root / "paper" / "paper.db"
    # paper and live are distinct
    assert paths.paper_ledger != paths.live
    assert paths.paper_ledger.is_relative_to(root / "paper")
    assert paths.live == root / "live"
    assert paths.live_decisions == root / "live" / "decisions"
    assert paths.live_ledger == root / "live" / "ledger"
    assert paths.models_metalabel == root / "models" / "metalabel"
    assert paths.models_metalabel.is_dir()
    assert paths.cache_events_hyperliquid == root / "cache" / "events" / "hyperliquid"
    assert paths.cache_events_hyperliquid.is_dir()


def test_ensure_data_layout_idempotent(tmp_path: Path):
    root = tmp_path / "data"
    ensure_data_layout(root)
    ensure_data_layout(root)
    assert (root / "cache").is_dir()
    assert (root / "paper" / "decisions").is_dir()


def test_paths_for_does_not_create(tmp_path: Path):
    root = tmp_path / "missing"
    p = paths_for(root)
    assert not root.exists()
    assert p.cache == root / "cache"


def test_layout_report_after_ensure(tmp_path: Path):
    root = tmp_path / "data"
    ensure_data_layout(root)
    rep = layout_report(root)
    assert rep["rules"]["paper_live_separated"] is True
    assert rep["dirs"]["paper_ledger"]["exists"] is True
    assert rep["dirs"]["live"]["exists"] is True
    assert rep["dirs"]["live_decisions"]["exists"] is True
    assert rep["dirs"]["live_ledger"]["exists"] is True
