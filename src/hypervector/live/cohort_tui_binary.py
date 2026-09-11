"""Explicit, authenticated prebuilt TUI selection without an implicit build."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import subprocess
from typing import Protocol


@dataclass(frozen=True)
class VerifiedTuiBinary:
    """Retain the selected absolute executable and its expected identity."""

    path: Path
    sha256: str

    def verify(self) -> None:
        """Refuse missing, non-executable, unreadable or changed binary content."""
        if not self.path.is_file() or not os.access(self.path, os.X_OK):
            raise RuntimeError(f"TUI binary must be an executable file: {self.path}")
        try:
            with self.path.open("rb") as source:
                observed = hashlib.file_digest(source, "sha256").hexdigest()
        except OSError as exc:
            raise RuntimeError(f"cannot read TUI binary: {self.path}") from exc
        if observed != self.sha256:
            raise RuntimeError(f"TUI binary SHA256 differs: {self.path}")


class TuiBinaryLaunch(Protocol):
    """The executable identity and foreground command used by a supervisor."""

    tui_command: tuple[str, ...]
    tui_binary: VerifiedTuiBinary | None


def load_tui_binary(path: Path | None, sha256: str | None) -> VerifiedTuiBinary | None:
    """Resolve a complete explicit selection and verify it before child startup."""
    if path is None and sha256 is None:
        return None
    if path is None or sha256 is None:
        raise RuntimeError("prebuilt TUI requires both --tui-bin and --tui-bin-sha256")
    if re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        raise RuntimeError(
            "--tui-bin-sha256 requires 64 lowercase hexadecimal characters"
        )
    binary = VerifiedTuiBinary(path.expanduser().resolve(), sha256)
    binary.verify()
    return binary


def verify_tui_command(
    command: tuple[str, ...], binary: VerifiedTuiBinary | None
) -> None:
    """Bind a selected executable to its command and recheck its current bytes."""
    if binary is None:
        return
    if not command or command[0] != str(binary.path):
        raise RuntimeError("TUI command differs from the verified binary selection")
    binary.verify()


def run_tui(launch: TuiBinaryLaunch) -> int:
    """Verify immediately before foreground invocation and propagate exit status."""
    verify_tui_command(launch.tui_command, launch.tui_binary)
    return subprocess.run(launch.tui_command, check=False).returncode
