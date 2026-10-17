"""Read-only host boot identity for the cohort supervisor.

Every reader returns None when its value is unknowable, and callers fail closed
on None. Nothing here signals, launches or writes anything. This module imports
only the standard library so it can run as an isolated child interpreter.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import subprocess
import sys

SYSCTL = "/usr/sbin/sysctl"
# <utmpx.h> record types.
BOOT_TIME_RECORD = 2
SHUTDOWN_TIME_RECORD = 11
# The current boot's own wtmpx record matches kern.boottime at boot, but macOS
# moves kern.boottime with later clock adjustments (2026-09-26: 0.16 s within
# an hour of boot), so the match allows a small step.
_CURRENT_BOOT_TOLERANCE_SECONDS = 60.0
_BOOT_SECONDS = re.compile(r"sec\s*=\s*(\d+)\s*,\s*usec\s*=\s*(\d+)")
_SESSION_UUID = re.compile(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}")

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True)
class BootIdentity:
    """This boot, read once when the supervisor starts."""

    session_uuid: str | None
    boot_time_epoch: float | None


def read_boot_identity(run: Runner = subprocess.run) -> BootIdentity:
    """Return kern.bootsessionuuid and kern.boottime; unknown parts are None.

    The session UUID is unique per boot and immune to clock steps, so it is the
    "same boot?" test. The boot time is evidence and an ordering bound only.
    """
    return BootIdentity(
        parse_boot_session(_sysctl("kern.bootsessionuuid", run)),
        parse_boot_time(_sysctl("kern.boottime", run)),
    )


def parse_boot_session(raw: str | None) -> str | None:
    """Accept exactly one UUID, normalised to upper case."""
    if raw is None:
        return None
    text = raw.strip()
    return text.upper() if _SESSION_UUID.fullmatch(text) else None


def parse_boot_time(raw: str | None) -> float | None:
    """Parse ``{ sec = N, usec = M } ...`` into epoch seconds."""
    match = _BOOT_SECONDS.search(raw or "")
    if match is None:
        return None
    return int(match.group(1)) + int(match.group(2)) / 1_000_000.0


def previous_shutdown_epoch(
    boot_time: float, run: Runner = subprocess.run
) -> float | None:
    """Return when the boot before this one began shutting down, or None.

    macOS writes the SHUTDOWN_TIME record as userspace shutdown starts, before
    launchd sends SIGTERM to the agents (2026-09-26: record 22:49:07.10Z, the
    supervisor's stop latched about 0.2 s later). A boot that ended in power loss
    or a panic has no such record, and the answer is None.

    ctypes walks libc's wtmpx history in an isolated child interpreter, so a
    fault there cannot take the supervisor down with it.
    """
    try:
        result = run(
            [
                sys.executable,
                "-I",
                str(Path(__file__).resolve()),
                "previous-shutdown",
                repr(float(boot_time)),
            ],
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if result.returncode != 0:
        return None
    try:
        value = json.loads(result.stdout)
    except ValueError:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value > 0 else None


def select_previous_shutdown(
    records: Iterable[tuple[int, float]], boot_time: float
) -> float | None:
    """Pick the shutdown that ended the previous boot from newest-first records.

    The newest boot or shutdown record must be this boot's own BOOT_TIME record;
    the next one must be a SHUTDOWN_TIME record older than this boot. Anything
    else (a history that does not start at this boot, or a previous boot with
    no shutdown record) is unknowable and returns None.
    """
    current_seen = False
    for kind, stamp in records:
        if kind not in (BOOT_TIME_RECORD, SHUTDOWN_TIME_RECORD):
            continue
        if not current_seen:
            if (
                kind != BOOT_TIME_RECORD
                or abs(stamp - boot_time) > _CURRENT_BOOT_TOLERANCE_SECONDS
            ):
                return None
            current_seen = True
            continue
        if kind == SHUTDOWN_TIME_RECORD and stamp < boot_time:
            return stamp
        return None
    return None


def _sysctl(name: str, run: Runner) -> str | None:
    try:
        result = run(
            [SYSCTL, "-n", name],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return result.stdout if result.returncode == 0 else None


def _wtmpx_records() -> Iterator[tuple[int, float]]:
    """Yield (ut_type, epoch) newest first from the host's wtmpx history."""
    import ctypes
    import ctypes.util

    class _Timeval(ctypes.Structure):
        _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_int32)]

    class _Utmpx(ctypes.Structure):
        # <utmpx.h>: 640 bytes on 64-bit macOS.
        _fields_ = [
            ("ut_user", ctypes.c_char * 256),
            ("ut_id", ctypes.c_char * 4),
            ("ut_line", ctypes.c_char * 32),
            ("ut_pid", ctypes.c_int32),
            ("ut_type", ctypes.c_short),
            ("ut_tv", _Timeval),
            ("ut_host", ctypes.c_char * 256),
            ("ut_pad", ctypes.c_uint32 * 16),
        ]

    if ctypes.sizeof(_Utmpx) != 640:
        return
    libc = ctypes.CDLL(ctypes.util.find_library("c"))
    libc.getutxent_wtmp.restype = ctypes.POINTER(_Utmpx)
    libc.setutxent_wtmp.argtypes = [ctypes.c_int]
    libc.setutxent_wtmp(0)  # zero reads newest first
    try:
        while True:
            entry = libc.getutxent_wtmp()
            if not entry:
                return
            record = entry.contents
            yield (
                int(record.ut_type),
                (record.ut_tv.tv_sec + record.ut_tv.tv_usec / 1_000_000.0),
            )
    finally:
        libc.endutxent_wtmp()


def main(argv: Sequence[str] | None = None) -> int:
    """Child entry point: print the previous boot's shutdown epoch as JSON."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "previous-shutdown":
        print(
            "usage: cohort_supervisor_host.py previous-shutdown BOOT_EPOCH",
            file=sys.stderr,
        )
        return 2
    boot_time = float(args[1])
    print(json.dumps(select_previous_shutdown(_wtmpx_records(), boot_time)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
