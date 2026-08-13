"""Deterministic execution-source selection for cohort live backups."""

from __future__ import annotations

from pathlib import Path

_ENTRYPOINT = Path("scripts/multi_asset_bidirectional_live.py")
_LOCK_FILES = (Path("pyproject.toml"), Path("uv.lock"))
_PACKAGE = Path("src/hypervector")
_EXCLUDED_PARTS = frozenset({"__pycache__"})
_MAX_SOURCE_FILES = 4096


def discover_cohort_implementation_sources(
    repository_root: Path,
    provider_root: Path,
) -> dict[str, Path]:
    """Return every bounded source file required to reproduce live startup."""
    repository = repository_root.resolve()
    provider = provider_root.resolve()
    package = _required_directory(repository / _PACKAGE, "Hypervector package")
    provider_package = _required_directory(provider, "provider package")
    repository_files = [
        _required_file(repository / _ENTRYPOINT, "cohort entrypoint"),
        *(
            _required_file(repository / relative, "dependency lock metadata")
            for relative in _LOCK_FILES
        ),
        *_python_sources(package),
    ]
    provider_files = _python_sources(provider_package)
    if not provider_files:
        raise ValueError(f"provider package contains no Python source: {provider}")
    return _role_map(repository_files, provider_files)


def _python_sources(root: Path) -> list[Path]:
    candidates = sorted(root.rglob("*.py"))
    selected = [
        _required_file(path, "implementation source")
        for path in candidates
        if not _excluded(path.relative_to(root))
    ]
    if len(selected) > _MAX_SOURCE_FILES:
        raise ValueError(
            f"implementation source count exceeds {_MAX_SOURCE_FILES}: {root}"
        )
    return selected


def _role_map(repository: list[Path], provider: list[Path]) -> dict[str, Path]:
    combined = [
        *((f"repository_{index:04d}", path) for index, path in enumerate(repository)),
        *((f"provider_{index:04d}", path) for index, path in enumerate(provider)),
    ]
    values = [path for _role, path in combined]
    if len(values) != len(set(values)):
        raise ValueError("implementation source paths must be unique")
    return dict(combined)


def _required_directory(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{label} cannot be a symlink: {path}")
    if not path.is_dir():
        raise ValueError(f"{label} is missing: {path}")
    return path


def _required_file(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{label} cannot be a symlink: {path}")
    if not path.is_file():
        raise ValueError(f"{label} is missing: {path}")
    return path.resolve()


def _excluded(relative: Path) -> bool:
    return any(
        part in _EXCLUDED_PARTS or part.startswith(".") for part in relative.parts
    )
