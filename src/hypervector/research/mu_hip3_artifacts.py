"""Recoverable immutable artifact publication for MU research commands."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from hypervector.data.oxa_storage import file_evidence


def require_new_outputs(*paths: Path) -> None:
    """Require distinct output targets that do not already exist."""
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError("immutable MU output paths must be distinct")
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(f"immutable MU outputs already exist: {existing}")


def staging_paths(*paths: Path) -> tuple[Path, ...]:
    """Return unique sibling staging paths for one artifact bundle."""
    token = uuid4().hex
    return tuple(path.with_name(f"{path.name}.mu-stage-{token}") for path in paths)


def staged_file_reference(
    final_path: Path, staged_path: Path, rows: int
) -> dict[str, object]:
    """Reference final location with evidence calculated from staged bytes."""
    if not staged_path.is_file():
        raise FileNotFoundError(f"MU staged evidence does not exist: {staged_path}")
    return {
        "path": str(final_path.resolve()),
        **file_evidence(staged_path),
        "rows": rows,
    }


def publish_bundle(pairs: tuple[tuple[Path, Path], ...]) -> None:
    """Hard-link a staged bundle and roll back every final on failure."""
    published: list[Path] = []
    try:
        for staged, final in pairs:
            final.parent.mkdir(parents=True, exist_ok=True)
            os.link(staged, final)
            published.append(final)
    except BaseException:
        for path in published:
            path.unlink(missing_ok=True)
        raise
