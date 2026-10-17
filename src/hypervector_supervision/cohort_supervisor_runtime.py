"""Cohort supervisor runtime."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import os
import json
from pathlib import Path
import signal
import subprocess
import sys

from hypervector_supervision.cohort_supervisor_models import (
    SupervisorPaths,
    HealthThresholds,
    RestartPolicy,
    REPOSITORY_ROOT,
    EXIT_START_REFUSED,
    EXIT_STOP_INCOMPLETE,
)
from hypervector_supervision.cohort_supervisor_health import (
    evaluate_health,
    free_disk_gib,
    read_lock_pid,
)
from hypervector_supervision.cohort_supervisor_alerts import (
    Alerter,
    append_jsonl,
)
from hypervector_supervision.cohort_supervisor_host import BootIdentity
from hypervector_supervision.cohort_supervisor_state import (
    SIGNAL_STOP_HOLDS,
    UNRESOLVED_SESSION_HOLD,
    RestartJournal,
    supervisor_lock,
)
from hypervector_supervision.cohort_supervisor_restart_policy import (
    charges_restart_budget,
    decide_host_restart_resume,
    decide_restart as decide_restart,
)
from hypervector_supervision.cohort_supervisor_venue_wait import (
    VenueWait,
    backend_venue_wait,
)
from hypervector_supervision.cohort_supervisor_observation import (
    _StopFlag,
    SupervisorRuntime,
    wait_for_adopted_exit,
)

HELD_AT_START_TITLE = "HYPERVECTOR SUPERVISOR HELD AT START"
HELD_TITLE = "HYPERVECTOR SUPERVISOR HELD"
RELAUNCHING_AFTER_HOST_RESTART_TITLE = "HYPERVECTOR RELAUNCHING AFTER HOST RESTART"
# The checkout's own interpreter, so the alert's command runs as written from any
# directory (a bare "python" may not be the venv that has hypervector installed).
RESUME_HELPER = (
    f"{REPOSITORY_ROOT / '.venv' / 'bin' / 'python'} -m hypervector "
    "live supervisor resume"
)
RESUME_AUTHORITY = "--yes --enabled --i-accept-live-risk"


def supervise(
    command: Sequence[str],
    paths: SupervisorPaths,
    thresholds: HealthThresholds,
    policy: RestartPolicy,
    alerter: Alerter,
    *,
    interval: float = 30.0,
    working_directory: Path = REPOSITORY_ROOT,
    adopt: bool = False,
    adopted_exit_policy: str = "hold",
    deadman_url: str | None = None,
    runtime: SupervisorRuntime | None = None,
    stop: _StopFlag | None = None,
    maximum_launches: int | None = None,
    resume_after_host_restart: bool = False,
) -> int:
    """Own one child with a durable budget and exclusive supervisor lock.

    ``resume_after_host_restart`` is the operator's opt-in (see
    RESUME_AFTER_HOST_RESTART_ENV) to release, at start, a hold that only the
    previous boot's shutdown latched.
    """
    runtime, stop = runtime or SupervisorRuntime(), stop or _StopFlag()
    with ExitStack() as scope:
        try:
            scope.enter_context(supervisor_lock(paths.events))
            boot = runtime.boot_identity()
            journal = RestartJournal(
                paths.events,
                command,
                boot_session=boot.session_uuid,
                clock=runtime.now,
            )
            session = _Session(
                command,
                paths,
                thresholds,
                policy,
                alerter,
                runtime,
                stop,
                journal,
                interval,
                working_directory,
                deadman_url,
                maximum_launches,
                boot,
                resume_after_host_restart,
            )
        except (ValueError, OSError) as exc:
            _event(paths, "supervisor_start_refused", reason=str(exc))
            return EXIT_START_REFUSED
        return session.run(adopt, adopted_exit_policy)


@dataclass
class _Session:
    """One exclusive, journal-bound supervisor lifetime."""

    command: Sequence[str]
    paths: SupervisorPaths
    thresholds: HealthThresholds
    policy: RestartPolicy
    alerter: Alerter
    runtime: SupervisorRuntime
    stop: _StopFlag
    journal: RestartJournal
    interval: float
    working_directory: Path
    deadman_url: str | None
    maximum_launches: int | None
    boot: BootIdentity = BootIdentity(None, None)
    resume_after_host_restart: bool = False
    charge_next_launch: bool = True
    child_log_offset: int = 0
    # Why an opt-in resume kept the start-time hold; None when not evaluated.
    resume_declined: str | None = None
    # Whether this session adopted a backend it found running.
    adopted: bool = False

    def run(self, adopt: bool, adopted_exit_policy: str) -> int:
        """Supervise, converting any unexpected fault into a monitored hold.

        Returning a nonzero code here would hand an armed, possibly position-holding
        child back to launchd's KeepAlive with nothing supervising it. The child is
        never killed on a supervisor fault: it is alerted and kept under health
        polling instead.
        """
        try:
            return self._run(adopt, adopted_exit_policy)
        except Exception as exc:
            reason = f"supervisor_faulted:{type(exc).__name__}"
            self.journal.hold(reason)
            _fault_event(self.paths, "supervisor_faulted", reason=type(exc).__name__)
            self.alerter.emit(
                "HYPERVECTOR SUPERVISOR FAULTED",
                reason,
                {"exception_type": type(exc).__name__},
                self.runtime.now(),
            )
            return _hold(
                self.paths,
                self.thresholds,
                self.alerter,
                self.stop,
                self.runtime,
                self.interval,
                reason,
                self.deadman_url,
            )

    def _run(self, adopt: bool, adopted_exit_policy: str) -> int:
        """Reconcile existing ownership, then launch only while explicitly permitted."""
        adopted_result = self._adopt(adopt, adopted_exit_policy)
        if adopted_result is not None:
            return adopted_result
        # Only when adoption found no backend: one that ran in this boot is
        # evidence the start-time hold is not the previous boot's shutdown.
        if self.resume_after_host_restart and not self.adopted:
            self._resume_after_host_restart()
        launches = 0
        while not self.stop.requested:
            if self.maximum_launches is not None and launches >= self.maximum_launches:
                return 3
            if self.paths.stop_file.exists():
                self.journal.hold("operator_stop_file_present")
                _event(
                    self.paths,
                    "restart_decision",
                    action="hold",
                    reason=self.journal.hold_reason,
                )
                return self._finish_hold()
            starved = self._insufficient_free_disk()
            if starved is not None:
                return starved
            if not self.journal.reserve(
                self.runtime.now(), self.policy, charged=self.charge_next_launch
            ):
                _event(
                    self.paths,
                    "restart_decision",
                    action="give_up",
                    reason=self.journal.hold_reason,
                )
                return self._held(launches)
            launches += 1
            exit_code = self._launch(launches)
            result = self._after_exit(exit_code)
            if result is not None:
                return result
        if self.journal.hold_reason is not None:
            # A stop that arrived before the first launch leaves an existing hold
            # (or the unended session that re-infers one) exactly as it was.
            # Latching over it would re-stamp it with this boot, or turn a hold
            # no restart releases into a signal stop that one would.
            return 0
        self.journal.hold("operator_signal_stop")
        return self._finish_hold()

    def _resume_after_host_restart(self) -> None:
        """Release a hold that only the previous boot's shutdown latched.

        Runs after adoption found no live backend, and only on the operator's
        opt-in. decide_host_restart_resume holds every other case; a release
        that cannot be written keeps the hold, and so does a stop (SIGTERM)
        that arrives before the release, since no launch would follow it. The
        launch that follows is charged to the restart budget as usual.
        """
        if self.journal.hold_reason is None or self.stop.requested:
            return
        pid = read_lock_pid(self.paths.process_lock)
        decision = decide_host_restart_resume(
            self.journal,
            self.boot,
            previous_shutdown=self.runtime.previous_shutdown,
            stop_file_present=self.paths.stop_file.exists(),
            backend_alive=pid is not None and self.runtime.is_backend(pid),
            free_disk_gib=free_disk_gib(self.paths.ledger),
            minimum_free_disk_gib=self.thresholds.minimum_free_disk_gib,
        )
        evidence = {**decision.evidence, "decision": decision.reason}
        if decision.resume and self.stop.requested:
            # The shutdown-history read can take seconds; a stop during it wins.
            decision = replace(decision, resume=False, reason="stop_requested")
            evidence["decision"] = decision.reason
        if decision.resume and not self.journal.release_after_host_restart():
            decision = replace(
                decision, resume=False, reason="restart_journal_unwritable"
            )
            evidence["decision"] = decision.reason
        if not decision.resume:
            self.resume_declined = decision.reason
            _event(self.paths, "host_restart_resume_declined", **evidence)
            return
        _event(self.paths, "hold_cleared_after_host_restart", **evidence)
        self.alerter.emit(
            RELAUNCHING_AFTER_HOST_RESTART_TITLE,
            str(evidence["previous_reason"]),
            evidence,
            self.runtime.now(),
        )

    def _held(self, launches: int) -> int:
        """Stay alive on a refused launch reservation, reminding until stopped.

        A hold read at start (RunAtLoad after a reboot) used to exit 0 silently,
        and launchd never relaunches a clean exit: on 2026-09-26 the book stayed
        dark for 29 minutes with no alert naming the latch. A SIGTERM ends this
        loop without latching anything new, so the original hold, and its stamp,
        stay exactly as they were.
        """
        reason = self.journal.hold_reason or "restart_refused"
        at_start = launches == 0 and not self.adopted
        title = HELD_AT_START_TITLE if at_start else HELD_TITLE
        resumable = reason in SIGNAL_STOP_HOLDS or reason == UNRESOLVED_SESSION_HOLD
        if not self.journal.hold_persisted:
            body = (
                f"{reason}; hold not persisted: restore write access to the "
                "restart journal, then restart the supervisor"
            )
        elif resumable:
            body = (
                f"{reason}; run {RESUME_HELPER} as a dry run first, then "
                f"with {RESUME_AUTHORITY}"
            )
        else:
            body = f"{reason}; archive the restart journal to resume"
        record = {
            "hold_reason": reason,
            "hold_persisted": self.journal.hold_persisted,
            "held_at_epoch": self.journal.held_at_epoch,
            "held_boot_session": self.journal.held_boot_session,
            "boot_session": self.boot.session_uuid,
            "resume_after_host_restart": self.resume_after_host_restart,
            "resume_declined": self.resume_declined,
        }

        def remind(now: float) -> None:
            self.alerter.emit(title, body, record, now)

        remind(self.runtime.now())
        return _hold(
            self.paths,
            self.thresholds,
            self.alerter,
            self.stop,
            self.runtime,
            self.interval,
            reason,
            self.deadman_url,
            remind=remind,
            remind_seconds=self.alerter.reminder_seconds,
        )

    def _insufficient_free_disk(self) -> int | None:
        """Refuse a launch the volume cannot hold, before it is charged.

        Every armed start writes a multi-gigabyte pre-start bundle before it can
        reach any refusal, so a restart loop on a nearly full volume consumes the
        space the live ledgers are still growing into. This is a technical
        precondition, not a strategy gate.

        A hold already in the journal already refuses the launch and is kept
        as it is, so a full volume at the first start after a reboot does not
        replace the previous boot's hold, or its stamp, with this one.
        """
        free = free_disk_gib(self.paths.ledger)
        minimum = self.thresholds.minimum_free_disk_gib
        if free is not None and free >= minimum:
            return None
        reason = "insufficient_free_disk"
        kept = self.journal.hold_reason
        _event(
            self.paths,
            "refused_insufficient_free_disk",
            free_disk_gib=free,
            minimum_free_disk_gib=minimum,
            kept_hold_reason=kept,
        )
        if kept is None:
            self.journal.hold(reason)
        self.alerter.emit(
            "HYPERVECTOR DISK EXHAUSTED",
            reason,
            {
                "free_disk_gib": free,
                "minimum_free_disk_gib": minimum,
                "hold_reason": self.journal.hold_reason,
            },
            self.runtime.now(),
        )
        return _hold(
            self.paths,
            self.thresholds,
            self.alerter,
            self.stop,
            self.runtime,
            self.interval,
            reason,
            self.deadman_url,
        )

    def _adopt(self, adopt: bool, policy: str) -> int | None:
        existing = read_lock_pid(self.paths.process_lock)
        if existing is None or not self.runtime.is_backend(existing):
            return None
        self.adopted = adopt
        if not adopt:
            # Exiting nonzero here would make launchd relaunch every
            # ThrottleInterval into the same refusal, with zero health polling and
            # zero alerts, for as long as the orphaned backend survives.
            _event(self.paths, "refused_backend_already_running", pid=existing)
            self.alerter.emit(
                "HYPERVECTOR BACKEND UNSUPERVISED",
                "backend_already_running_without_adopt",
                {"pid": existing},
                self.runtime.now(),
            )
            return _hold(
                self.paths,
                self.thresholds,
                self.alerter,
                self.stop,
                self.runtime,
                self.interval,
                "backend_already_running_without_adopt",
                self.deadman_url,
            )
        _event(self.paths, "adopted_running_backend", pid=existing, exit_policy=policy)
        ended = wait_for_adopted_exit(
            self.paths,
            self.thresholds,
            self.alerter,
            self.stop,
            self.runtime,
            interval=self.interval,
            deadman_url=self.deadman_url,
        )
        if not ended:
            return 0
        _event(self.paths, "adopted_backend_ended", pid=existing)
        if self.paths.stop_file.exists() or policy != "restart":
            reason = (
                "operator_stop_file_present"
                if self.paths.stop_file.exists()
                else "adopted_exit_status_unobservable"
            )
            self.journal.hold(reason)
            self.alerter.emit(
                "HYPERVECTOR BACKEND ENDED",
                reason,
                {"pid": existing},
                self.runtime.now(),
            )
            return _hold(
                self.paths,
                self.thresholds,
                self.alerter,
                self.stop,
                self.runtime,
                self.interval,
                reason,
                self.deadman_url,
            )
        return None

    def _launch(self, launches: int) -> int:
        started = self.runtime.now()
        self.paths.child_log.parent.mkdir(parents=True, exist_ok=True)
        with self.paths.child_log.open("ab", buffering=0) as log:
            log.write(
                f"\n=== supervisor launch {launches} at {datetime.fromtimestamp(started, UTC).isoformat()} ===\n".encode()
            )
            self.child_log_offset = log.tell()
            child = subprocess.Popen(
                list(self.command),
                cwd=self.working_directory,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        _event(self.paths, "backend_launched", pid=child.pid, launch=launches)
        code = _watch_child(
            child,
            self.paths,
            self.thresholds,
            self.policy,
            self.alerter,
            self.stop,
            self.runtime,
            interval=self.interval,
            started=started,
            deadman_url=self.deadman_url,
            on_stop=lambda: self.journal.hold("operator_signal_stop"),
        )
        _event(
            self.paths,
            "backend_exited",
            pid=child.pid,
            exit_code=code,
            uptime_seconds=round(self.runtime.now() - started, 3),
        )
        return code

    def _after_exit(self, code: int) -> int | None:
        if self.stop.requested:
            self.journal.hold(
                "operator_stop_grace_expired"
                if code == EXIT_STOP_INCOMPLETE
                else "operator_signal_stop"
            )
            return self._finish_hold()
        decision = decide_restart(
            code,
            stop_file_present=self.paths.stop_file.exists(),
            restart_times=self.journal.launch_times[1:],
            policy=self.policy,
            now=self.runtime.now(),
        )
        refusal = (
            _start_refusal_reason(self.paths.child_log, self.child_log_offset)
            if code == EXIT_START_REFUSED
            else None
        )
        _event(
            self.paths,
            "restart_decision",
            **asdict(decision),
            exit_code=code,
            **({} if refusal is None else {"refusal_reason": refusal}),
        )
        self.charge_next_launch = charges_restart_budget(code)
        if decision.action != "restart":
            self.journal.hold(decision.reason)
        if decision.action == "stop":
            return self._finish_hold()
        title = "HYPERVECTOR BACKEND RESTARTING"
        if decision.action == "give_up":
            title = "HYPERVECTOR SUPERVISOR GAVE UP"
        elif decision.action == "hold":
            title = "HYPERVECTOR BACKEND HELD"
        self.alerter.emit(
            title,
            decision.reason,
            {"exit_code": code, **asdict(decision)},
            self.runtime.now(),
        )
        if decision.action == "give_up":
            return 1 if self.journal.hold_persisted else self._finish_hold()
        if decision.action == "hold":
            return _hold(
                self.paths,
                self.thresholds,
                self.alerter,
                self.stop,
                self.runtime,
                self.interval,
                decision.reason,
                self.deadman_url,
            )
        _interruptible_sleep(decision.delay_seconds, self.stop, self.runtime)
        return None

    def _finish_hold(self) -> int:
        """Exit only when the stop is durable; otherwise retain monitored ownership."""
        if self.journal.hold_persisted:
            return 0
        reason = self.journal.hold_reason or "restart_journal_unwritable"
        self.alerter.emit(
            "HYPERVECTOR STOP NOT PERSISTED",
            reason,
            {"hold_persisted": False},
            self.runtime.now(),
        )
        return _hold(
            self.paths,
            self.thresholds,
            self.alerter,
            self.stop,
            self.runtime,
            self.interval,
            reason,
            self.deadman_url,
        )


def _watch_child(
    child: subprocess.Popen[bytes],
    paths: SupervisorPaths,
    thresholds: HealthThresholds,
    policy: RestartPolicy,
    alerter: Alerter,
    stop: _StopFlag,
    runtime: SupervisorRuntime,
    *,
    interval: float,
    started: float,
    deadman_url: str | None,
    on_stop: Callable[[], None] | None = None,
) -> int:
    """Poll one owned child until it ends, alerting on health as it runs.

    A hung-but-alive backend is alerted, never killed: an open position keeps its
    venue-native stop, and SIGTERM is the operator-stop path, so killing on a
    heuristic would convert a telemetry problem into an execution event.

    A backend waiting for the venue before its start is announced as waiting,
    not reported as a stale heartbeat: its startup grace begins when the wait
    ends, because its ledger replay and engine starts only begin then.
    """
    grace_anchor, waiting = started, False
    while True:
        code = child.poll()
        if code is not None:
            return code
        if stop.requested:
            if on_stop is not None:
                on_stop()
            if _terminate_group(child):
                return child.wait()
            _event(paths, "operator_stop_grace_expired", pid=child.pid)
            alerter.emit(
                "HYPERVECTOR BACKEND WOULD NOT STOP",
                "operator_stop_grace_expired",
                {"pid": child.pid},
                runtime.now(),
            )
            code = child.poll()
            return EXIT_STOP_INCOMPLETE if code is None else code
        now = runtime.now()
        wait = backend_venue_wait(paths.process_lock, child.pid, now)
        if wait is not None:
            grace_anchor = now
            if not waiting:
                _announce_venue_wait(paths, alerter, wait, now)
        waiting = wait is not None
        warming = now - grace_anchor < policy.startup_grace_seconds
        report = evaluate_health(
            paths,
            thresholds,
            now=now,
            is_backend=lambda _pid: True,
            heartbeat_required=not warming,
        )
        alerter.observe(report, now)
        runtime.deadman(deadman_url)
        _interruptible_sleep(interval, stop, runtime)


_REFUSAL_PREFIX = "live start refused: "
_REFUSAL_TAIL_BYTES = 64 * 1024
_REFUSAL_MAXIMUM_CHARACTERS = 500


def _start_refusal_reason(child_log: Path, offset: int) -> str | None:
    """Return the backend's own refusal line from this launch's output, if any.

    Only bytes written after this launch's header are read, so an earlier
    launch's refusal is never attributed to this one. The reason stays in the
    local event journal, beside the log it was copied from.
    """
    try:
        with child_log.open("rb") as handle:
            end = handle.seek(0, os.SEEK_END)
            handle.seek(max(offset, end - _REFUSAL_TAIL_BYTES))
            tail = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        if line.startswith(_REFUSAL_PREFIX):
            reason = line[len(_REFUSAL_PREFIX) :].strip()
            return reason[:_REFUSAL_MAXIMUM_CHARACTERS] or None
    return None


def _announce_venue_wait(
    paths: SupervisorPaths, alerter: Alerter, wait: VenueWait, now: float
) -> None:
    detail = asdict(wait)
    _event(paths, "backend_waiting_for_venue", **detail)
    alerter.emit(
        "HYPERVECTOR BACKEND WAITING FOR VENUE",
        "backend_waiting_for_venue",
        detail,
        now,
    )


def _hold(
    paths: SupervisorPaths,
    thresholds: HealthThresholds,
    alerter: Alerter,
    stop: _StopFlag,
    runtime: SupervisorRuntime,
    interval: float,
    reason: str,
    deadman_url: str | None = None,
    *,
    remind: Callable[[float], None] | None = None,
    remind_seconds: float = 1_800.0,
) -> int:
    """Stay alive and keep reminding. Exiting would let launchd relaunch a loop.

    ``remind`` re-sends the caller's own notice every ``remind_seconds``; the
    caller sent the first one. The wait between polls checks the stop flag
    every second: a held supervisor now stays alive, and a signal does not cut
    a sleep short (PEP 475), so a bootout or ``kickstart -k`` would otherwise
    wait out a full interval.
    """
    _fault_event(paths, "holding", reason=reason)
    reminded = runtime.now()
    while not stop.requested:
        now = runtime.now()
        if remind is not None and now - reminded >= remind_seconds:
            remind(now)
            reminded = now
        alerter.observe(
            evaluate_health(paths, thresholds, now=now, is_backend=runtime.is_backend),
            now,
        )
        runtime.deadman(deadman_url)
        _interruptible_sleep(interval, stop, runtime)
    return 0


def _terminate_group(
    child: subprocess.Popen[bytes], grace_seconds: float = 30.0
) -> bool:
    """Forward the operator's graceful stop and report whether the child ended.

    An armed backend is never escalated to SIGKILL: it may hold a position whose
    protective orders are mid-flight, so an unfinished stop is alerted and left for
    the operator rather than forced.
    """
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    try:
        child.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        return False
    return True


def _interruptible_sleep(
    seconds: float, stop: _StopFlag, runtime: SupervisorRuntime
) -> None:
    deadline = runtime.now() + seconds
    while not stop.requested and runtime.now() < deadline:
        runtime.sleep(min(1.0, max(0.0, deadline - runtime.now())))


def _event(paths: SupervisorPaths, name: str, **fields: object) -> None:
    append_jsonl(
        paths.events,
        {"event": name, "at_utc": datetime.now(UTC).isoformat(), **fields},
    )


def _fault_event(paths: SupervisorPaths, name: str, **fields: object) -> None:
    """Report failed event durability without breaking fault-state supervision."""
    try:
        _event(paths, name, **fields)
    except OSError as exc:
        print(
            json.dumps(
                {
                    "event": "supervisor_event_delivery_failed",
                    "failed_event": name,
                    "exception_type": type(exc).__name__,
                    "durable": False,
                }
            ),
            file=sys.stderr,
            flush=True,
        )
