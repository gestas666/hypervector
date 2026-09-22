"""Cohort supervisor runtime."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import os
import json
from pathlib import Path
import signal
import subprocess
import sys

from cohort_supervisor_models import (
    SupervisorPaths,
    HealthThresholds,
    RestartPolicy,
    REPOSITORY_ROOT,
    EXIT_START_REFUSED,
    EXIT_STOP_INCOMPLETE,
)
from cohort_supervisor_health import (
    evaluate_health,
    free_disk_gib,
    read_lock_pid,
)
from cohort_supervisor_alerts import Alerter, append_jsonl
from cohort_supervisor_state import RestartJournal, supervisor_lock
from cohort_supervisor_restart_policy import decide_restart as decide_restart
from cohort_supervisor_observation import (
    _StopFlag, SupervisorRuntime, wait_for_adopted_exit,
)


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
) -> int:
    """Own one child with a durable budget and exclusive supervisor lock."""
    runtime, stop = runtime or SupervisorRuntime(), stop or _StopFlag()
    with ExitStack() as scope:
        try:
            scope.enter_context(supervisor_lock(paths.events))
            journal = RestartJournal(paths.events, command)
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
            if not self.journal.reserve(self.runtime.now(), self.policy):
                _event(
                    self.paths,
                    "restart_decision",
                    action="give_up",
                    reason=self.journal.hold_reason,
                )
                return self._finish_hold()
            launches += 1
            exit_code = self._launch(launches)
            result = self._after_exit(exit_code)
            if result is not None:
                return result
        self.journal.hold("operator_signal_stop")
        return self._finish_hold()

    def _insufficient_free_disk(self) -> int | None:
        """Refuse a launch the volume cannot hold, before it is charged.

        Every armed start writes a multi-gigabyte pre-start bundle before it can
        reach any refusal, so a restart loop on a nearly full volume consumes the
        space the live ledgers are still growing into. This is a technical
        precondition, not a strategy gate.
        """
        free = free_disk_gib(self.paths.ledger)
        minimum = self.thresholds.minimum_free_disk_gib
        if free is not None and free >= minimum:
            return None
        reason = "insufficient_free_disk"
        _event(
            self.paths,
            "refused_insufficient_free_disk",
            free_disk_gib=free,
            minimum_free_disk_gib=minimum,
        )
        self.journal.hold(reason)
        self.alerter.emit(
            "HYPERVECTOR DISK EXHAUSTED",
            reason,
            {"free_disk_gib": free, "minimum_free_disk_gib": minimum},
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
        _event(self.paths, "restart_decision", **asdict(decision), exit_code=code)
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
            "HYPERVECTOR STOP NOT PERSISTED", reason,
            {"hold_persisted": False}, self.runtime.now(),
        )
        return _hold(
            self.paths, self.thresholds, self.alerter, self.stop, self.runtime,
            self.interval, reason, self.deadman_url,
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
    """
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
        warming = now - started < policy.startup_grace_seconds
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


def _hold(
    paths: SupervisorPaths,
    thresholds: HealthThresholds,
    alerter: Alerter,
    stop: _StopFlag,
    runtime: SupervisorRuntime,
    interval: float,
    reason: str,
    deadman_url: str | None = None,
) -> int:
    """Stay alive and keep reminding. Exiting would let launchd relaunch a loop."""
    _fault_event(paths, "holding", reason=reason)
    while not stop.requested:
        now = runtime.now()
        alerter.observe(
            evaluate_health(paths, thresholds, now=now, is_backend=runtime.is_backend),
            now,
        )
        runtime.deadman(deadman_url)
        runtime.sleep(interval)
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
            json.dumps({
                "event": "supervisor_event_delivery_failed", "failed_event": name,
                "exception_type": type(exc).__name__, "durable": False,
            }),
            file=sys.stderr, flush=True,
        )
