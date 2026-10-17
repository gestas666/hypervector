"""Deterministic execution-source selection for cohort live backups."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import Path

from hypervector.live.cohort_backup_identity import build_implementation_identity

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
        *_package_sources(package),
        *_supervision_sources(package),
    ]
    provider_files = _python_sources(provider_package)
    if not provider_files:
        raise ValueError(f"provider package contains no Python source: {provider}")
    return _role_map(repository_files, provider_files)


def discover_installed_cohort_sources(
    provider_root: Path,
    *,
    package_root: Path | None = None,
) -> dict[str, Path]:
    """Bind installed Python, CLI option resources and bundled dependency metadata."""
    package = package_root or Path(__file__).resolve().parents[1]
    metadata = [
        _required_file(package / "_build" / name, "dependency lock metadata")
        for name in ("pyproject.toml", "uv.lock")
    ]
    _required_file(
        package / "operations" / "multi_asset_bidirectional_live.py",
        "cohort entrypoint",
    )
    provider = _python_sources(
        _required_directory(provider_root.resolve(), "provider package")
    )
    if not provider:
        raise ValueError(f"provider package contains no Python source: {provider_root}")
    return _role_map(
        [*metadata, *_package_sources(package), *_supervision_sources(package)],
        provider,
    )


def _supervision_sources(package: Path) -> list[Path]:
    """Bind any independent supervision package shipped beside the trading code."""
    companion = package.parent / "hypervector_supervision"
    if not companion.exists():
        return []
    return _python_sources(_required_directory(companion, "supervision package"))


def _package_sources(package: Path) -> list[Path]:
    resources = sorted((package / "commands").rglob("*.json"))
    selected = [
        *_python_sources(package),
        *(_required_file(path, "CLI option contract") for path in resources),
    ]
    if len(selected) > _MAX_SOURCE_FILES:
        raise ValueError(
            f"implementation source count exceeds {_MAX_SOURCE_FILES}: {package}"
        )
    return selected


def implementation_source_identity(sources: Mapping[str, Path]) -> dict[str, object]:
    """Return the content identity a pre-start backup would record for ``sources``.

    It hashes each file's bytes under its role exactly as the bundle's
    implementation identity does, so two discoveries compare by content and by
    the set of files, without writing anything.
    """
    records = [
        {
            "role": f"implementation_{role}",
            "source_bytes": size,
            "source_sha256": digest,
        }
        for role, (digest, size) in (
            (role, _digest(path)) for role, path in sorted(sources.items())
        )
    ]
    identity = build_implementation_identity(records)
    if identity is None:
        raise ValueError("implementation sources are required")
    return identity


def _digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


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
