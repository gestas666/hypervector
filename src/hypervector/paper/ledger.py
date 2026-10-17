"""Append-only paper decision ledger.

Accepts ``execution_mode`` in ``{paper, shadow}`` under the paper root;
defaults to ``paper`` when missing or invalid. Requires a feed timestamp,
writes under ``data/paper/decisions/``, and refuses any path that resolves
under ``data/live/``. Never enables live write paths and never creates the
live directory tree.

Each record is one ``os.write`` of a complete JSON line under an exclusive
``flock``. A short or failed write is rolled back. A torn final line left by a
crash or a full disk is repaired before the next append: a complete JSON
object only gains its missing newline; an incomplete fragment is copied
byte-for-byte to a ``decisions.jsonl.torn-<UTC>`` sidecar, truncated away and
recorded by one ``ledger_tail_quarantined`` audit row. A new record is never
merged into a fragment.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hypervector.infra import DATA_SUBDIRS, DataPaths, paths_for

logger = logging.getLogger(__name__)

EXECUTION_MODE = "paper"
ALLOWED_EXECUTION_MODES = frozenset({"paper", "shadow"})
DECISIONS_FILENAME = "decisions.jsonl"
FEED_TS_KEY = "feed_ts"
QUARANTINE_ACTION = "ledger_tail_quarantined"
TORN_SIDECAR_INFIX = ".torn-"
_FEED_TS_ALIASES = (FEED_TS_KEY, "feed_timestamp")
_TAIL_SCAN_BYTES = 64 * 1024
# Indirection so tests can simulate a short write without patching ``os``.
_write = os.write


class PaperLedgerError(ValueError):
    """Invalid paper decision record or forbidden write path."""


def ensure_paper_layout(root: Path | str) -> DataPaths:
    """Create the I2 data layout except the ``live`` tree (paper never owns it)."""
    paths = paths_for(root)
    if "live" in paths.root.resolve().parts:
        raise PaperLedgerError(
            f"refusing paper layout under live path ({paths.root.resolve()})"
        )
    paths.root.mkdir(parents=True, exist_ok=True)
    for rel in DATA_SUBDIRS:
        if rel == "live" or rel.startswith("live/"):
            continue
        (paths.root / rel).mkdir(parents=True, exist_ok=True)
    return paths


def _resolve_feed_ts(record: dict[str, Any]) -> Any:
    for key in _FEED_TS_ALIASES:
        if key in record and record[key] is not None and record[key] != "":
            return record[key]
    raise PaperLedgerError(
        "paper decision record must include a feed timestamp "
        f"({FEED_TS_KEY!r} or 'feed_timestamp')"
    )


def paper_decisions_file(data_root: Path | str) -> Path:
    """Validate and return the paper decisions JSONL path, creating only its dir.

    Refuses a data root under any ``live`` directory before creating anything,
    and refuses a decisions file that resolves (for example through a symlink)
    under ``live/`` or outside ``paper/decisions``. Paths are re-validated on
    every call; symlink-free components below the resolved root are joined
    instead of re-resolved, which is exactly what ``realpath`` would return.
    """
    root = os.fspath(data_root)
    real_root = os.path.realpath(root)
    if "live" in Path(real_root).parts:
        raise PaperLedgerError(f"refusing paper write under live path ({real_root})")
    dest_dir = os.path.join(root, "paper", "decisions")
    real_live = _realpath_below(root, real_root, ("live",))
    real_dest = _realpath_below(root, real_root, ("paper", "decisions"))
    # Refuse a symlinked paper/ or paper/decisions/ into live/ before mkdir.
    if "live" in Path(real_dest).parts or _within(real_dest, real_live):
        raise PaperLedgerError(f"refusing paper write under live path ({real_dest})")
    os.makedirs(dest_dir, exist_ok=True)
    out_path = os.path.join(dest_dir, DECISIONS_FILENAME)
    real_out = _realpath_below(dest_dir, real_dest, (DECISIONS_FILENAME,))
    if "live" in Path(real_out).parts or _within(real_out, real_live):
        raise PaperLedgerError(f"refusing paper write under live path ({real_out})")
    if os.path.dirname(real_out) != real_dest:
        raise PaperLedgerError(
            f"refusing paper write outside paper/decisions ({out_path})"
        )
    return Path(out_path)


def _realpath_below(base: str, real_base: str, parts: tuple[str, ...]) -> str:
    """Return ``realpath(base/parts)`` given ``real_base == realpath(base)``."""
    current = base
    resolved = real_base
    for part in parts:
        current = os.path.join(current, part)
        if os.path.islink(current):
            return os.path.realpath(os.path.join(base, *parts))
        resolved = os.path.join(resolved, part)
    return resolved


def _within(path: str, ancestor: str) -> bool:
    return path == ancestor or path.startswith(ancestor.rstrip(os.sep) + os.sep)


def append_paper_decision(data_root: Path | str, record: dict[str, Any]) -> Path:
    """Append one paper decision JSON line under ``data/paper/decisions/``.

    Stamps ``execution_mode`` from the record when it is in
    :data:`ALLOWED_EXECUTION_MODES` (``paper``|``shadow``); otherwise defaults
    to ``paper``. Never force-overwrites a valid ``shadow``. Requires
    ``feed_ts`` (or ``feed_timestamp`` alias, normalized to ``feed_ts``).
    Creates only ``paper/decisions`` (never ``live/``). Returns the decisions
    JSONL path.

    Raises:
        PaperLedgerError: missing feed timestamp, or destination under live/.
        OSError: the write failed; the ledger is restored to its prior size.
    """
    if not isinstance(record, dict):
        raise PaperLedgerError("record must be a dict")

    feed_ts = _resolve_feed_ts(record)
    out_path = paper_decisions_file(data_root)

    payload = dict(record)
    payload.pop("feed_timestamp", None)
    payload[FEED_TS_KEY] = feed_ts
    mode = record.get("execution_mode")
    if mode not in ALLOWED_EXECUTION_MODES:
        mode = EXECUTION_MODE
    payload["execution_mode"] = mode

    encoded = _encode_line(payload)
    _append_encoded_line(out_path, encoded, execution_mode=str(mode))
    return out_path


def _encode_line(payload: dict[str, Any]) -> bytes:
    line = json.dumps(payload, default=str, separators=(",", ":"))
    return (line + "\n").encode("utf-8")


def _append_encoded_line(path: Path, encoded: bytes, *, execution_mode: str) -> None:
    fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        size = os.fstat(fd).st_size
        if size and os.pread(fd, 1, size - 1) != b"\n":
            size = _repair_torn_tail(fd, path, size, execution_mode=execution_mode)
        _write_or_rollback(fd, encoded, size)
    finally:
        os.close(fd)


def _write_or_rollback(fd: int, encoded: bytes, size: int) -> int:
    """Write one complete line or truncate back to ``size`` and raise."""
    try:
        written = _write(fd, encoded)
    except OSError:
        _truncate_quietly(fd, size)
        raise
    if written != len(encoded):
        _truncate_quietly(fd, size)
        raise OSError(
            errno.EIO,
            f"short paper ledger write ({written} of {len(encoded)} bytes)",
        )
    return size + written


def _truncate_quietly(fd: int, size: int) -> None:
    try:
        os.ftruncate(fd, size)
    except OSError:  # the next append repairs any remaining torn tail
        logger.exception("paper ledger rollback truncate failed")


def _last_newline_offset(fd: int, size: int) -> int:
    """Return the offset of the last ``\\n`` before ``size``, or -1."""
    end = size
    while end > 0:
        start = max(0, end - _TAIL_SCAN_BYTES)
        block = os.pread(fd, end - start, start)
        index = block.rfind(b"\n")
        if index >= 0:
            return start + index
        end = start
    return -1


def _repair_torn_tail(fd: int, path: Path, size: int, *, execution_mode: str) -> int:
    """Terminate or quarantine an unterminated final line; return the new size."""
    keep = _last_newline_offset(fd, size) + 1
    fragment = os.pread(fd, size - keep, keep)
    if _is_complete_record(fragment):
        logger.warning("paper ledger %s: terminating unterminated final record", path)
        return _write_or_rollback(fd, b"\n", size)
    sidecar = _write_sidecar(path, fragment)
    os.ftruncate(fd, keep)
    logger.warning(
        "paper ledger %s: quarantined %d torn tail bytes to %s",
        path,
        len(fragment),
        sidecar,
    )
    audit = _encode_line(
        {
            "feed_ts": datetime.now(timezone.utc).isoformat(),
            "action": QUARANTINE_ACTION,
            "torn_bytes": len(fragment),
            "torn_sha256": hashlib.sha256(fragment).hexdigest(),
            "sidecar": str(sidecar),
            "execution_mode": execution_mode,
            "submitted": False,
        }
    )
    return _write_or_rollback(fd, audit, keep)


def _is_complete_record(fragment: bytes) -> bool:
    try:
        return isinstance(json.loads(fragment.decode("utf-8")), dict)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False


def _write_sidecar(path: Path, fragment: bytes) -> Path:
    """Durably preserve the original torn bytes beside the ledger."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for attempt in range(100):
        suffix = f"{TORN_SIDECAR_INFIX}{stamp}" + (f"-{attempt}" if attempt else "")
        sidecar = path.with_name(path.name + suffix)
        try:
            fd = os.open(sidecar, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            continue
        try:
            view = memoryview(fragment)
            while view:
                view = view[os.write(fd, view) :]
            os.fsync(fd)
        finally:
            os.close(fd)
        return sidecar
    raise OSError(errno.EEXIST, f"cannot allocate torn-tail sidecar for {path}")
