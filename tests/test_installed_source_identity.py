"""An installed runtime must retain reproducible implementation-source evidence."""

from pathlib import Path

import pytest

from hypervector.live.cohort_implementation_sources import (
    discover_installed_cohort_sources,
)


def test_installed_identity_includes_lock_metadata_and_command_contract(
    tmp_path: Path,
) -> None:
    """A wheel must bind the live entry point, declarative options and dependencies."""
    package = tmp_path / "hypervector"
    for name in [
        "operations/multi_asset_bidirectional_live.py",
        "_build/pyproject.toml",
        "_build/uv.lock",
        "commands/specs/cohort.json",
    ]:
        target = package / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}" if name.endswith("json") else "fixture")
    sources = discover_installed_cohort_sources(package_root=package)
    assert set(sources.values()) == {
        path.resolve() for path in package.rglob("*") if path.is_file()
    }


def test_installed_runtime_refuses_missing_dependency_lock(tmp_path: Path) -> None:
    """Missing wheel provenance must be a start failure, not an empty identity."""
    with pytest.raises(ValueError, match="metadata|lock"):
        discover_installed_cohort_sources(package_root=tmp_path)


def test_installed_identity_binds_independent_supervision_sources(
    tmp_path: Path,
) -> None:
    """A watcher/restart policy change must alter the implementation evidence."""
    package = tmp_path / "hypervector"
    for name in [
        "operations/multi_asset_bidirectional_live.py",
        "_build/pyproject.toml",
        "_build/uv.lock",
    ]:
        target = package / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture")
    supervisor = tmp_path / "hypervector_supervision/cohort_backend_supervisor.py"
    supervisor.parent.mkdir()
    supervisor.write_text('"""independent supervisor fixture"""')
    sources = discover_installed_cohort_sources(package_root=package)
    assert supervisor.resolve() in sources.values()
