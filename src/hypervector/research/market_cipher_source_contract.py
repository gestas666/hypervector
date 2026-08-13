"""Read-only source identity for recovered Market Cipher strategy evidence."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import subprocess


_SCALPER_FILES = ("HAND.toml", "SKILL.md")
_EXECUTABLE_ROOTS = ("src/mcc", "config/default.toml", "tools/autotune")
_EXCLUDED_NAMES = {".DS_Store", ".env", "__pycache__"}


def audit_market_cipher_sources(
    mc_scalper_root: Path,
    market_cipher_cli_root: Path,
) -> dict[str, object]:
    """Return immutable identities without importing either external project."""
    scalper = mc_scalper_root.resolve()
    executable = market_cipher_cli_root.resolve()
    _require_files(scalper, _SCALPER_FILES, "MC scalper")
    _require_files(
        executable,
        ("src/mcc/engine.py", "config/default.toml"),
        "Market Cipher CLI",
    )
    skill_text = (scalper / "SKILL.md").read_text(encoding="utf-8")
    return {
        "report_only": True,
        "execution_authority": "none",
        "place_attempted": False,
        "mc_scalper": {
            "root": str(scalper),
            "runtime": _runtime(skill_text),
            "executable_strategy": False,
            "source_tree_sha256": _selected_tree_sha256(scalper, _SCALPER_FILES),
        },
        "market_cipher_cli": {
            "root": str(executable),
            "executable_strategy": True,
            "git_commit": _git_text(executable, "rev-parse", "HEAD"),
            "worktree_dirty": bool(
                _git_bytes(
                    executable, "status", "--porcelain=v1", "--untracked-files=all"
                )
            ),
            "worktree_state_sha256": _git_state_sha256(executable),
            "source_tree_sha256": _selected_tree_sha256(executable, _EXECUTABLE_ROOTS),
        },
    }


def _runtime(skill_text: str) -> str:
    """Extract the declared prompt runtime from the skill front matter."""
    for line in skill_text.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip() == "runtime":
            runtime = value.strip().strip("\"'")
            if runtime:
                return runtime
    raise ValueError("MC scalper SKILL.md is missing a runtime declaration")


def _require_files(root: Path, relative_paths: tuple[str, ...], label: str) -> None:
    """Fail with all missing source paths for one evidence root."""
    if not root.is_dir():
        raise FileNotFoundError(f"{label} root does not exist: {root}")
    missing = [
        relative for relative in relative_paths if not (root / relative).exists()
    ]
    if missing:
        raise FileNotFoundError(f"{label} source files missing: {missing}")


def _selected_tree_sha256(root: Path, selected: tuple[str, ...]) -> str:
    """Hash a stable allowlist of files and directories below a source root."""
    digest = sha256()
    files: set[Path] = set()
    for relative in selected:
        candidate = root / relative
        if candidate.is_file():
            files.add(candidate)
        elif candidate.is_dir():
            files.update(path for path in candidate.rglob("*") if _included(path))
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _included(path: Path) -> bool:
    """Return whether a path is an allowed regular source artifact."""
    return (
        path.is_file()
        and not any(part in _EXCLUDED_NAMES for part in path.parts)
        and path.suffix != ".pyc"
    )


def _git_state_sha256(root: Path) -> str:
    """Hash tracked changes and status metadata without exposing file contents."""
    digest = sha256()
    digest.update(_git_bytes(root, "diff", "--binary", "HEAD"))
    digest.update(_git_bytes(root, "status", "--porcelain=v1", "--untracked-files=all"))
    return digest.hexdigest()


def _git_text(root: Path, *arguments: str) -> str:
    """Run a read-only git command and decode its stripped output."""
    return _git_bytes(root, *arguments).decode("utf-8").strip()


def _git_bytes(root: Path, *arguments: str) -> bytes:
    """Run a read-only git command and return stdout bytes."""
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout
