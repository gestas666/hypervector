"""Source discovery prunes excluded directories with an unchanged selection.

The reference is the original selection: ``sorted(root.rglob("*.py"))`` with
dot-directories, hidden files and ``__pycache__`` filtered out afterwards, then
``_required_file`` on every remaining candidate in that order.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

from hypervector.live import cohort_implementation_sources as sources

_SCANNED: list[str] | None = None


def _audit(event: str, args: tuple[object, ...]) -> None:
    if _SCANNED is not None and event == "os.scandir" and args:
        _SCANNED.append(os.fsdecode(args[0]) if args[0] is not None else ".")


sys.addaudithook(_audit)


def _reference(root: Path) -> list[Path]:
    candidates = sorted(root.rglob("*.py"))
    return [
        sources._required_file(path, "implementation source")
        for path in candidates
        if not sources._excluded(path.relative_to(root))
    ]


def _outcome(select, root: Path) -> tuple[str, object]:  # noqa: ANN001
    try:
        return ("ok", select(root))
    except ValueError as exc:
        return ("error", str(exc))


def _tree(root: Path) -> None:
    files = [
        "a.py",
        "pkg/__init__.py",
        "pkg/b.py",
        "pkg/deep/c.py",
        "pkg/deep/notes.txt",
        "pkg/.hidden.py",
        "pkg/__pycache__/b.cpython-313.py",
        ".venv/lib/site.py",
        ".git/hooks/x.py",
        "pkg/.cache/d.py",
        "zz/e.py",
        "A_upper.py",
        "pkg/name.PY",
    ]
    for relative in files:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("X = 1\n", encoding="utf-8")
    outside = root.parent / "outside"
    (outside / "inner").mkdir(parents=True, exist_ok=True)
    (outside / "inner" / "f.py").write_text("X = 2\n", encoding="utf-8")
    (root / "linked_dir").symlink_to(outside / "inner", target_is_directory=True)
    (root / ".hidden_link.py").symlink_to(outside / "inner" / "f.py")


_HAZARDS = {
    "directory_named_py": lambda root: (root / "pkg" / "module.py").mkdir(),
    "file_symlink": lambda root: (root / "pkg" / "link.py").symlink_to(root / "a.py"),
    "dir_symlink_named_py": lambda root: (root / "zz" / "dir.py").symlink_to(
        root / "pkg", target_is_directory=True
    ),
    "broken_symlink": lambda root: (root / "broken.py").symlink_to(root / "missing.py"),
    "hidden_hazards_only": lambda root: (root / ".venv" / "dir.py").mkdir(),
}


def test_clean_tree_selection_is_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "provider"
    _tree(root)
    expected = _reference(root)
    assert sources._python_sources(root) == expected
    assert [path.name for path in expected] == [
        "A_upper.py",
        "a.py",
        "__init__.py",
        "b.py",
        "c.py",
        "e.py",
    ]


@pytest.mark.parametrize("hazard", sorted(_HAZARDS))
def test_refusals_are_unchanged(tmp_path: Path, hazard: str) -> None:
    root = tmp_path / "provider"
    _tree(root)
    _HAZARDS[hazard](root)
    assert _outcome(sources._python_sources, root) == _outcome(_reference, root)


def test_excluded_directories_are_never_listed(tmp_path: Path) -> None:
    """Dot-directories and caches are pruned instead of walked and discarded."""
    global _SCANNED
    root = tmp_path / "provider"
    _tree(root)
    for index in range(50):
        path = root / ".venv" / "lib" / f"pkg{index}" / "mod.py"
        path.parent.mkdir(parents=True)
        path.write_text("X = 3\n", encoding="utf-8")
    _SCANNED = []
    try:
        selected = sources._python_sources(root)
        scanned = list(_SCANNED)
    finally:
        _SCANNED = None
    assert selected == _reference(root)
    assert scanned
    assert not [
        path for path in scanned if sources._excluded(Path(path).relative_to(root))
    ]
