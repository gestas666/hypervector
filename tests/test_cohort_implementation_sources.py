"""Tests for deterministic live implementation source discovery."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest


def _discover() -> object:
    try:
        module = import_module("hypervector.live.cohort_implementation_sources")
    except ModuleNotFoundError:
        pytest.fail("cohort implementation discovery module is missing")
    discover = getattr(module, "discover_cohort_implementation_sources", None)
    assert discover is not None, "cohort implementation discovery API is missing"
    return discover


def _seed_roots(tmp_path: Path) -> tuple[Path, Path, set[Path]]:
    repo = tmp_path / "hypervector"
    provider = tmp_path / "backtest-lab" / "backtest_lab"
    expected = {
        repo / "src/hypervector/live/engine.py",
        repo / "src/hypervector/strategies/signal.py",
        repo / "scripts/multi_asset_bidirectional_live.py",
        repo / "pyproject.toml",
        repo / "uv.lock",
        provider / "provider.py",
    }
    for path in expected:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"SOURCE = {path.name!r}\n", encoding="utf-8")
    (repo / ".env").write_text("SECRET=excluded\n", encoding="utf-8")
    (provider / "cache.json").write_text("{}\n", encoding="utf-8")
    cached = repo / "src/hypervector/__pycache__/generated.py"
    cached.parent.mkdir(parents=True)
    cached.write_text("SHOULD_NOT_LOAD = True\n", encoding="utf-8")
    return repo, provider, {path.resolve() for path in expected}


def test_discovers_complete_bounded_execution_source_set(tmp_path: Path) -> None:
    """Startup snapshots code and lock metadata without secret or cache files."""
    repo, provider, expected = _seed_roots(tmp_path)

    sources = _discover()(repo, provider)

    assert set(sources.values()) == expected
    assert len(sources) == len(set(sources))
    assert all(role.startswith(("repository_", "provider_")) for role in sources)


def test_rejects_symlinked_execution_source(tmp_path: Path) -> None:
    """A source snapshot cannot follow an unexpected link outside its root."""
    repo, provider, _expected = _seed_roots(tmp_path)
    external = tmp_path / "external.py"
    external.write_text("SECRET = True\n", encoding="utf-8")
    link = provider / "linked.py"
    link.symlink_to(external)

    with pytest.raises(ValueError, match="symlink"):
        _discover()(repo, provider)
