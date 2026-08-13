"""Exact loaded-source provenance for long-running HIP-3 diagnostics."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

from hypervector.data.oxa_storage import file_evidence


def loaded_project_source_paths(
    project_root: Path,
    invoked_script: Path,
) -> tuple[Path, ...]:
    """Return currently loaded project Python sources plus lock inputs."""
    root = project_root.resolve()
    paths = {
        path
        for module in tuple(sys.modules.values())
        if (path := _module_source(module)) is not None and _within_root(path, root)
    }
    paths.update(
        {
            invoked_script.resolve(),
            root / "pyproject.toml",
            root / "uv.lock",
        }
    )
    return tuple(sorted(paths))


def source_dependency_identity(
    project_root: Path,
    paths: tuple[Path, ...],
) -> dict[str, object]:
    """Hash an explicit, non-empty set of project dependency files."""
    root = project_root.resolve()
    resolved = tuple(sorted({path.resolve() for path in paths}))
    if not resolved:
        raise ValueError("HIP-3 dependency identity requires source paths")
    for path in resolved:
        if not _within_root(path, root):
            raise ValueError(f"HIP-3 dependency is outside project root: {path}")
        if not path.is_file():
            raise FileNotFoundError(f"HIP-3 dependency does not exist: {path}")
    evidence = {str(path.relative_to(root)): file_evidence(path) for path in resolved}
    return {"tree_sha256": _tree_hash(evidence), "files": evidence}


def require_unchanged_dependencies(
    expected: dict[str, object],
    project_root: Path,
) -> None:
    """Fail when any dependency recorded at start changed before publication."""
    root = project_root.resolve()
    files = expected.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("HIP-3 expected dependency evidence is invalid")
    paths = tuple(root / str(relative) for relative in files)
    observed = source_dependency_identity(root, paths)
    if observed != expected:
        raise RuntimeError("HIP-3 dependency source changed during evaluation")


def require_unchanged_file(path: Path, expected: dict[str, object]) -> None:
    """Compare one file to a path-decorated immutable evidence reference."""
    checksum = expected.get("sha256")
    byte_count = expected.get("bytes")
    valid_bytes = isinstance(byte_count, int) and not isinstance(byte_count, bool)
    if not isinstance(checksum, str) or not checksum or not valid_bytes:
        raise ValueError("HIP-3 expected file evidence is invalid")
    frozen = {"sha256": checksum, "bytes": byte_count}
    if file_evidence(path) != frozen:
        raise ValueError(f"HIP-3 input changed during evaluation: {path}")


def _module_source(module: object) -> Path | None:
    raw = getattr(module, "__file__", None)
    if not isinstance(raw, str):
        return None
    path = Path(raw).resolve()
    if path.suffix == ".pyc":
        candidate = path.with_suffix("")
        return candidate if candidate.is_file() else None
    return path if path.suffix == ".py" and path.is_file() else None


def _within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return False
    return True


def _tree_hash(evidence: dict[str, dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for relative, value in evidence.items():
        digest.update(relative.encode("utf-8"))
        digest.update(str(value["sha256"]).encode("ascii"))
    return digest.hexdigest()
