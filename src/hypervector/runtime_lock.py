"""Advisory process locks for singleton backend runtimes."""

from __future__ import annotations

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO

_LIVE_ACCOUNT_LOCK_NAME = "shared-account.lock"
_CHECKPOINT_WRITER_LOCK_SUFFIX = ".writer.lock"
_GENERIC_LIVE_LOCK = "generic_live/process.lock"
_GENERIC_LIVE_LABEL = "generic live daemon"
_SOURCE_ROOT = Path(__file__).resolve().parents[2]
# Same resolution as the cohort supervisor's REPOSITORY_ROOT: the launchd cohort
# runs from the checkout, so its relative data/live ledger lands under it.
_REPOSITORY_ROOT = (
    _SOURCE_ROOT
    if (_SOURCE_ROOT / "pyproject.toml").is_file()
    else Path.cwd().resolve()
)


class RuntimeLockError(RuntimeError):
    """A backend runtime cannot acquire exclusive process ownership."""


def canonical_live_root() -> Path:
    """The shared live account's lock root: the armed cohort's ``data/live``.

    Absolute and independent of any ``--data-root``, so a live executor cannot
    move its shared-account lock away from the one the cohort holds.
    """
    return _REPOSITORY_ROOT / "data" / "live"


@contextmanager
def cohort_checkpoint_runtime_lock(checkpoint_output: Path) -> Iterator[Path]:
    """Hold exclusive ownership of one bounded cohort checkpoint output."""
    lock_path = _checkpoint_writer_lock_path(checkpoint_output)
    with _runtime_lock(lock_path, "cohort checkpoint writer"):
        yield lock_path


def cohort_checkpoint_writer_active(checkpoint_output: Path) -> bool:
    """Return whether another process owns the checkpoint output lock."""
    lock_path = _checkpoint_writer_lock_path(checkpoint_output)
    if not lock_path.is_file():
        return False
    descriptor = os.open(lock_path, os.O_RDWR)
    with os.fdopen(descriptor, "r+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return False


def _checkpoint_writer_lock_path(checkpoint_output: Path) -> Path:
    return checkpoint_output.parent / (
        checkpoint_output.name + _CHECKPOINT_WRITER_LOCK_SUFFIX
    )


@contextmanager
def bidirectional_live_runtime_lock(live_ledger: Path) -> Iterator[Path]:
    """Own one shared account for the live cohort."""
    lock_path = live_ledger.parent / "process.lock"
    live_root = live_ledger.parent.parent
    other_owners = (
        (
            live_ledger.parent / "observer.lock",
            "bidirectional cohort observer",
        ),
        (live_root / _GENERIC_LIVE_LOCK, _GENERIC_LIVE_LABEL),
    )
    with _runtime_lock(lock_path, "bidirectional live cohort"):
        with _shared_live_account_lock(live_root):
            _refuse_active_owners(other_owners)
            yield lock_path


@contextmanager
def generic_live_runtime_lock(live_root: Path) -> Iterator[Path]:
    """Own the shared account for the generic single-export ``live run`` daemon.

    ``live_root`` must be the account's canonical root (:func:`canonical_live_root`),
    never an operator ``--data-root``: the lock only serializes against the
    cohort when it lands next to its lock.
    """
    lock_path = live_root / _GENERIC_LIVE_LOCK
    other_owners = (
        (
            live_root / "bidirectional_cohort/process.lock",
            "bidirectional live cohort",
        ),
    )
    with _runtime_lock(lock_path, _GENERIC_LIVE_LABEL):
        with _shared_live_account_lock(live_root):
            _refuse_active_owners(other_owners)
            yield lock_path


@contextmanager
def bidirectional_observer_runtime_lock(live_ledger: Path) -> Iterator[Path]:
    """Own the execution-incapable cohort observer ledger writer."""
    lock_path = live_ledger.parent / "observer.lock"
    with _runtime_lock(lock_path, "bidirectional cohort observer"):
        _refuse_active_owner(
            live_ledger.parent / "process.lock",
            "bidirectional live cohort",
        )
        yield lock_path


@contextmanager
def _shared_live_account_lock(live_root: Path) -> Iterator[None]:
    """Serialize independently launched strategies sharing one live account."""
    lock_path = live_root / _LIVE_ACCOUNT_LOCK_NAME
    with _runtime_lock(lock_path, "shared live account"):
        yield


def _refuse_active_owners(owners: tuple[tuple[Path, str], ...]) -> None:
    for lock_path, label in owners:
        _refuse_active_owner(lock_path, label)


def _refuse_active_owner(lock_path: Path, label: str) -> None:
    if not lock_path.is_file():
        return
    descriptor = os.open(lock_path, os.O_RDWR)
    with os.fdopen(descriptor, "r+", encoding="utf-8") as handle:
        acquired = False
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError as exc:
            handle.seek(0)
            owner = handle.read().strip() or "unknown"
            raise RuntimeLockError(
                f"{label} already owns the shared account "
                f"(pid={owner}, lock={lock_path})"
            ) from exc
        finally:
            if acquired:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _runtime_lock(lock_path: Path, label: str) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+", encoding="utf-8") as handle:
        _acquire(handle, lock_path, label)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _acquire(handle: TextIO, lock_path: Path, label: str) -> None:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.seek(0)
        owner = handle.read().strip() or "unknown"
        raise RuntimeLockError(
            f"{label} already running (pid={owner}, lock={lock_path})"
        ) from exc
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
