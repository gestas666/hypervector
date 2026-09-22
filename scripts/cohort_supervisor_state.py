"""Durable restart accounting and exclusive supervisor ownership."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from cohort_supervisor_models import RestartPolicy


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

    def __init__(self, events: Path, command: Sequence[str]) -> None:
        """Bind persistence to exact argv without recording command contents."""
        self.path = events.with_name(events.stem + "_restart_state.json")
        self.command_sha256 = hashlib.sha256(
            json.dumps(list(command)).encode()
        ).hexdigest()
        self.launch_times: list[float] = []
        self.hold_reason: str | None = None
        self.hold_persisted = True
        self.session_active = False
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
        self.launch_times, self.hold_reason = list(times), reason
        self.session_active = active
        if active and reason is None:
            self.hold_reason = "previous_supervisor_session_unresolved"
            self.hold_persisted = False

    def reserve(self, now: float, policy: RestartPolicy) -> bool:
        """Charge a launch before process creation; exhausted history latches a hold."""
        if self.hold_reason not in (None, "previous_supervisor_session_unresolved"):
            return False
        if any(stamp > now for stamp in self.launch_times):
            self.hold("restart_clock_moved_backwards")
            return False
        recent = [
            stamp for stamp in self.launch_times if now - stamp <= policy.window_seconds
        ]
        if len(recent) >= policy.maximum_restarts + 1:
            self.hold("restart_budget_exhausted")
            return False
        if self.hold_reason is not None:
            self.hold(self.hold_reason)
            return False
        self.launch_times = [*recent, now]
        was_active = self.session_active
        self.session_active = True
        if not self._save():
            # An uncounted launch would let every relaunch re-read an empty budget
            # and retry the armed backend without bound.
            self.launch_times = recent
            self.session_active = was_active
            self.hold("restart_journal_unwritable")
            return False
        return True

    def hold(self, reason: str) -> None:
        """Keep a stop durable until an operator explicitly archives this journal.

        A latch that cannot be written must not unwind into the caller: the
        in-memory hold still stands, and ``hold_persisted`` tells the supervisor to
        stay alive and keep alerting rather than exit into a launchd relaunch that
        would re-read the journal as "no hold".
        """
        self.hold_reason = reason
        was_active = self.session_active
        self.session_active = False
        self.hold_persisted = self._save()
        if not self.hold_persisted:
            self.session_active = was_active

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
