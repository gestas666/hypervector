"""Advisory process locks for singleton backend runtimes."""

from __future__ import annotations

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO

from hypervector.infra import ensure_data_layout

LOCK_NAME = "hypervelocity-shadow.lock"


@contextmanager
def hypervelocity_runtime_lock(data_root: Path) -> Iterator[Path]:
    """Hold the single Hypervelocity backend lock for one data root."""
    paths = ensure_data_layout(data_root)
    lock_path = paths.root / "paper" / LOCK_NAME
    with lock_path.open("a+", encoding="utf-8") as handle:
        _acquire(handle, lock_path)
        try:
            yield lock_path
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _acquire(handle: TextIO, lock_path: Path) -> None:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.seek(0)
        owner = handle.read().strip() or "unknown"
        raise RuntimeError(
            f"Hypervelocity backend already running for this data root "
            f"(pid={owner}, lock={lock_path})"
        ) from exc
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
