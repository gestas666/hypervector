"""An installed runtime must retain reproducible implementation-source evidence."""

from pathlib import Path

import pytest

from hypervector.live.cohort_implementation_sources import discover_installed_cohort_sources


def test_installed_identity_includes_lock_metadata_and_command_contract(tmp_path: Path) -> None:
    """A wheel must bind the live entry point, declarative options and dependencies."""
    package = tmp_path / "hypervector"
    provider = tmp_path / "provider"
    provider.mkdir()
    (provider / "__init__.py").write_text('"""fixture provider"""')
    for name in ["operations/multi_asset_bidirectional_live.py", "_build/pyproject.toml", "_build/uv.lock", "commands/specs/cohort.json"]:
        target = package / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}" if name.endswith("json") else "fixture")
    sources = discover_installed_cohort_sources(provider, package_root=package)
    assert set(sources.values()) == {path.resolve() for path in package.rglob("*") if path.is_file()} | {provider / "__init__.py"}


def test_installed_runtime_refuses_missing_dependency_lock(tmp_path: Path) -> None:
    """Missing wheel provenance must be a start failure, not an empty identity."""
    provider = tmp_path / "provider"
    provider.mkdir()
    with pytest.raises(ValueError, match="metadata|lock"):
        discover_installed_cohort_sources(provider, package_root=tmp_path)
