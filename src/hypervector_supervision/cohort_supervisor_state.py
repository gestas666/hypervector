"""Durable restart accounting and exclusive supervisor ownership."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time

from hypervector_supervision.cohort_supervisor_models import RestartPolicy

# Holds a SIGTERM/SIGINT to the supervisor latches. launchd sends exactly these
# on a host restart, shutdown or logout as well as on an operator bootout, so on
# their own they do not prove operator intent.
SIGNAL_STOP_HOLDS = frozenset({"operator_signal_stop", "operator_stop_grace_expired"})
UNRESOLVED_SESSION_HOLD = "previous_supervisor_session_unresolved"
_BOOT_SESSION_MAXIMUM_CHARACTERS = 64


def restart_journal_path(events: Path) -> Path:
    """Return the durable restart journal that sits beside an events journal."""
    return events.with_name(events.stem + "_restart_state.json")


@contextmanager
def supervisor_lock(events: Path) -> Iterator[None]:
    """Refuse concurrent supervisors, including during pre-start and backoff."""
    path = events.with_suffix(".supervisor.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("another supervisor owns the restart journal") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class RestartJournal:
    """Persist launches before spawning and retain operator/technical holds."""

    def __init__(
        self,
        events: Path,
        command: Sequence[str],
        *,
        boot_session: str | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Bind persistence to exact argv without recording command contents.

        ``boot_session`` is this boot's kern.bootsessionuuid, read once when the
        supervisor started; every hold and every launch reservation is stamped
        with it. None (unknown) stamps None, and an unstamped hold is never
        released after a host restart.
        """
        self.path = restart_journal_path(events)
        self.command_sha256 = hashlib.sha256(
            json.dumps(list(command)).encode()
        ).hexdigest()
        self._boot_session = boot_session
        self._clock = clock
        self.launch_times: list[float] = []
        self.hold_reason: str | None = None
        self.hold_persisted = True
        self.session_active = False
        # When and in which boot session the current hold latched, and the boot
        # session of the newest launch reservation. Absent (None) in journals
        # written before these fields existed.
        self.held_at_epoch: float | None = None
        self.held_boot_session: str | None = None
        self.launch_boot_session: str | None = None
        # True when the hold was inferred at load from a session that never
        # ended, rather than latched and written by a supervisor.
        self.hold_inferred_from_active_session = False
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text())
        except (OSError, ValueError, UnicodeError) as exc:
            raise ValueError(
                "restart journal unreadable; restore or archive it explicitly"
            ) from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("restart journal has invalid schema")
        if payload.get("command_sha256") != self.command_sha256:
            raise ValueError(
                "restart command changed; archive the journal at the approved boundary"
            )
        times, reason = payload.get("launch_times"), payload.get("hold_reason")
        if not isinstance(times, list) or any(
            isinstance(t, bool)
            or not isinstance(t, (int, float))
            or not math.isfinite(t)
            or t < 0
            for t in times
        ):
            raise ValueError("restart journal has invalid launch timestamps")
        if reason is not None and (not isinstance(reason, str) or not reason):
            raise ValueError("restart journal has invalid hold reason")
        active = payload.get("session_active", False)
        if not isinstance(active, bool):
            raise ValueError("restart journal has invalid session state")
        self.held_at_epoch = _optional_epoch(payload.get("held_at_epoch"))
        self.held_boot_session = _optional_session(payload.get("held_boot_session"))
        self.launch_boot_session = _optional_session(payload.get("launch_boot_session"))
        self.launch_times, self.hold_reason = list(times), reason
        self.session_active = active
        if active and reason is None:
            self.hold_reason = UNRESOLVED_SESSION_HOLD
            self.hold_persisted = False
            self.hold_inferred_from_active_session = True

    def reserve(
        self, now: float, policy: RestartPolicy, *, charged: bool = True
    ) -> bool:
        """Charge a launch before process creation; exhausted history latches a hold.

        An uncharged launch (the relaunch after a venue-blindness exit) still marks
        the session active before the spawn, so a supervisor crash in between
        holds exactly as it does for a charged one; it neither spends nor
        consults the crash budget.
        """
        if self.hold_reason not in (None, UNRESOLVED_SESSION_HOLD):
            return False
        if any(stamp > now for stamp in self.launch_times):
            self.hold("restart_clock_moved_backwards")
            return False
        recent = [
            stamp for stamp in self.launch_times if now - stamp <= policy.window_seconds
        ]
        if charged and len(recent) >= policy.maximum_restarts + 1:
            self.hold("restart_budget_exhausted")
            return False
        if self.hold_reason is not None:
            # Persist an inferred hold once, stamped with the boot that first
            # found the dead session. Re-latching one already on disk would
            # re-stamp it with every later boot and hide that it was seen before.
            if self.hold_inferred_from_active_session:
                self.hold(self.hold_reason)
            return False
        self.launch_times = [*recent, now] if charged else recent
        was_active, was_session = self.session_active, self.launch_boot_session
        self.session_active = True
        self.launch_boot_session = self._boot_session
        if not self._save():
            # An uncounted launch would let every relaunch re-read an empty budget
            # and retry the armed backend without bound.
            self.launch_times = recent
            self.session_active = was_active
            self.launch_boot_session = was_session
            self.hold("restart_journal_unwritable")
            return False
        return True

    def hold(self, reason: str) -> None:
        """Keep a stop durable until an operator explicitly archives this journal.

        The only other release is the operator's opt-in resume after a host
        restart, which needs this latch's time and boot session stamp.

        A latch that cannot be written must not unwind into the caller: the
        in-memory hold still stands, and ``hold_persisted`` tells the supervisor to
        stay alive and keep alerting rather than exit into a launchd relaunch that
        would re-read the journal as "no hold".
        """
        self.hold_reason = reason
        self.held_at_epoch = self._clock()
        self.held_boot_session = self._boot_session
        self.hold_inferred_from_active_session = False
        was_active = self.session_active
        self.session_active = False
        self.hold_persisted = self._save()
        if not self.hold_persisted:
            self.session_active = was_active

    def release_after_host_restart(self) -> bool:
        """Clear a hold the caller proved only a host restart latched.

        Returns whether the cleared state is durable. A journal that cannot be
        rewritten keeps the hold, in memory and on disk.
        """
        saved = (
            self.hold_reason,
            self.session_active,
            self.held_at_epoch,
            self.held_boot_session,
            self.hold_persisted,
            self.hold_inferred_from_active_session,
        )
        self.hold_reason, self.session_active = None, False
        self.held_at_epoch = self.held_boot_session = None
        self.hold_inferred_from_active_session = False
        if not self._save():
            (
                self.hold_reason,
                self.session_active,
                self.held_at_epoch,
                self.held_boot_session,
                self.hold_persisted,
                self.hold_inferred_from_active_session,
            ) = saved
            return False
        self.hold_persisted = True
        return True

    def _save(self) -> bool:
        """Persist atomically; report failure instead of raising into the loop."""
        try:
            self._write()
        except OSError:
            return False
        return True

    def _write(self) -> None:
        payload = {
            "schema_version": 1,
            "command_sha256": self.command_sha256,
            "launch_times": self.launch_times,
            "hold_reason": self.hold_reason,
            "session_active": self.session_active,
            "held_at_epoch": self.held_at_epoch,
            "held_boot_session": self.held_boot_session,
            "launch_boot_session": self.launch_boot_session,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            dir=self.path.parent, prefix=".restart-"
        )
        try:
            with os.fdopen(descriptor, "w") as handle:
                json.dump(payload, handle, allow_nan=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)


def _optional_epoch(value: object) -> float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("restart journal has invalid hold time")
    return float(value)


def _optional_session(value: object) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _BOOT_SESSION_MAXIMUM_CHARACTERS
    ):
        raise ValueError("restart journal has invalid boot session")
    return value
