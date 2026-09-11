"""Offline executable identity checks for the cohort's explicit TUI binary."""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path

import pytest


@pytest.fixture
def executable(tmp_path: Path) -> tuple[Path, str]:
    """Create inert executable bytes without running a process."""
    path = tmp_path / "tui with spaces"
    path.write_bytes(b"qualified inert executable fixture\n")
    path.chmod(0o700)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_explicit_executable_retains_verified_absolute_identity(
    executable: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Relative configuration resolves to the same executable and exact digest."""
    module = importlib.import_module("hypervector.live.cohort_tui_binary")
    path, digest = executable
    monkeypatch.chdir(path.parent)
    binary = module.load_tui_binary(Path(path.name), digest)
    assert binary.path == path
    assert binary.sha256 == digest
    binary.verify()


def test_no_explicit_selection_preserves_development_mode() -> None:
    """An absent pair selects no prebuilt executable."""
    module = importlib.import_module("hypervector.live.cohort_tui_binary")
    assert module.load_tui_binary(None, None) is None


@pytest.mark.parametrize("missing", ["path", "digest"])
def test_partial_selection_is_refused(
    executable: tuple[Path, str], missing: str
) -> None:
    """Neither an unauthenticated path nor an unbound digest is accepted."""
    module = importlib.import_module("hypervector.live.cohort_tui_binary")
    path, digest = executable
    with pytest.raises(RuntimeError, match="requires both"):
        module.load_tui_binary(
            None if missing == "path" else path,
            None if missing == "digest" else digest,
        )


@pytest.mark.parametrize("digest", ["", "a" * 63, "a" * 65, "G" * 64, "A" * 64])
def test_invalid_digest_is_refused(executable: tuple[Path, str], digest: str) -> None:
    """Malformed or noncanonical expected identities cannot authorize a binary."""
    module = importlib.import_module("hypervector.live.cohort_tui_binary")
    with pytest.raises(RuntimeError, match="64 lowercase hexadecimal"):
        module.load_tui_binary(executable[0], digest)


def test_wrong_digest_is_refused(executable: tuple[Path, str]) -> None:
    """A present executable with different bytes does not fall back to Cargo."""
    module = importlib.import_module("hypervector.live.cohort_tui_binary")
    with pytest.raises(RuntimeError, match="SHA256 differs"):
        module.load_tui_binary(executable[0], "0" * 64)


@pytest.mark.parametrize("kind", ["missing", "directory", "not_executable"])
def test_invalid_executable_is_refused(tmp_path: Path, kind: str) -> None:
    """Missing files, directories and non-executable files are explicit failures."""
    module = importlib.import_module("hypervector.live.cohort_tui_binary")
    path = tmp_path / "invalid"
    if kind == "directory":
        path.mkdir()
    elif kind == "not_executable":
        path.write_bytes(b"inert")
        path.chmod(0o600)
    with pytest.raises(RuntimeError, match="TUI binary"):
        module.load_tui_binary(path, "0" * 64)


def test_replacement_after_resolution_is_refused(
    executable: tuple[Path, str],
) -> None:
    """Later verification checks bytes again rather than trusting an old result."""
    module = importlib.import_module("hypervector.live.cohort_tui_binary")
    path, digest = executable
    binary = module.load_tui_binary(path, digest)
    path.write_bytes(b"replaced after resolution")
    with pytest.raises(RuntimeError, match="SHA256 differs"):
        binary.verify()


def test_unreadable_executable_reports_actionable_failure(
    executable: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Filesystem read errors retain the configured path and explicit failure."""
    module = importlib.import_module("hypervector.live.cohort_tui_binary")
    path, digest = executable
    binary = module.load_tui_binary(path, digest)

    def denied(*args: object, **kwargs: object) -> object:
        """Simulate the read boundary becoming inaccessible."""
        raise PermissionError("denied fixture")

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(RuntimeError, match="cannot read TUI binary"):
        binary.verify()


def test_verified_command_must_select_the_authenticated_path(
    executable: tuple[Path, str],
) -> None:
    """A different command cannot reuse another executable's qualification."""
    module = importlib.import_module("hypervector.live.cohort_tui_binary")
    binary = module.load_tui_binary(*executable)
    module.verify_tui_command((str(binary.path), "--help"), binary)
    with pytest.raises(RuntimeError, match="command differs"):
        module.verify_tui_command(("cargo", "run"), binary)
    with pytest.raises(RuntimeError, match="command differs"):
        module.verify_tui_command((), binary)
    module.verify_tui_command(("cargo", "run"), None)
