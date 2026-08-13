"""Deterministic generator provenance for immutable MU archive research."""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

from hypervector.data.oxa_storage import file_evidence


def source_tree_identity(
    project_root: Path,
    invoked_script: Path,
) -> dict[str, object]:
    """Hash the complete Python generator tree and dependency lock inputs."""
    root = project_root.resolve()
    paths = _identity_paths(root, invoked_script.resolve())
    evidence = {str(path.relative_to(root)): file_evidence(path) for path in paths}
    digest = hashlib.sha256()
    for relative, value in evidence.items():
        digest.update(relative.encode("utf-8"))
        digest.update(str(value["sha256"]).encode("ascii"))
    return {
        "tree_sha256": digest.hexdigest(),
        "files": evidence,
        "git_head": _git_output(root, "rev-parse", "HEAD"),
        "git_dirty": bool(_git_output(root, "status", "--porcelain")),
    }


def require_unchanged_generator(
    expected: dict[str, object],
    project_root: Path,
    invoked_script: Path,
) -> None:
    """Fail publication if generator inputs changed during a long replay."""
    observed = source_tree_identity(project_root, invoked_script)
    if observed != expected:
        raise RuntimeError("MU generator source tree changed during evaluation")


def _identity_paths(project_root: Path, invoked_script: Path) -> tuple[Path, ...]:
    paths = [
        *sorted((project_root / "src/hypervector").rglob("*.py")),
        invoked_script,
        project_root / "pyproject.toml",
        project_root / "uv.lock",
    ]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"MU generator identity inputs missing: {missing}")
    return tuple(sorted(set(paths)))


def _git_output(project_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode and arguments == ("rev-parse", "HEAD"):
        return "UNBORN"
    if completed.returncode:
        raise RuntimeError(
            f"git {' '.join(arguments)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()
