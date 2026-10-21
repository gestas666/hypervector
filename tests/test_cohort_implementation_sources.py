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


def _seed_repository(tmp_path: Path) -> tuple[Path, set[Path]]:
    repo = tmp_path / "hypervector"
    expected = {
        repo / "src/hypervector/live/engine.py",
        repo / "src/hypervector/live/provider_registry.py",
        repo / "src/hypervector/strategies/signal.py",
        repo / "src/hypervector/commands/specs/live/start.json",
        repo / "scripts/multi_asset_bidirectional_live.py",
        repo / "pyproject.toml",
        repo / "uv.lock",
    }
    for path in expected:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"SOURCE = {path.name!r}\n", encoding="utf-8")
    (repo / ".env").write_text("SECRET=excluded\n", encoding="utf-8")
    cached = repo / "src/hypervector/__pycache__/generated.py"
    cached.parent.mkdir(parents=True)
    cached.write_text("SHOULD_NOT_LOAD = True\n", encoding="utf-8")
    return repo, {path.resolve() for path in expected}


def test_discovers_complete_bounded_execution_source_set(tmp_path: Path) -> None:
    """Startup snapshots code, registry and lock metadata without secret or cache files."""
    repo, expected = _seed_repository(tmp_path)

    sources = _discover()(repo)

    assert set(sources.values()) == expected
    assert len(sources) == len(set(sources))
    assert all(role.startswith("repository_") for role in sources)


def test_rejects_symlinked_execution_source(tmp_path: Path) -> None:
    """A source snapshot cannot follow an unexpected link outside its root."""
    repo, _expected = _seed_repository(tmp_path)
    external = tmp_path / "external.py"
    external.write_text("SECRET = True\n", encoding="utf-8")
    link = repo / "src/hypervector/live/linked.py"
    link.symlink_to(external)

    with pytest.raises(ValueError, match="symlink"):
        _discover()(repo)


def test_a_missing_entrypoint_is_refused(tmp_path: Path) -> None:
    """An incomplete checkout cannot produce an empty or partial identity."""
    repo, _expected = _seed_repository(tmp_path)
    (repo / "scripts/multi_asset_bidirectional_live.py").unlink()

    with pytest.raises(ValueError, match="cohort entrypoint"):
        _discover()(repo)
