"""Venue blindness is not a crash: no budget charge, and a waiting backend is not hung.

The backend exits with its own code when the account stays unreconciled past the
wall-clock bound. Its relaunch waits in process for the venue before any bundle
or replay, so charging that relaunch to the crash budget would let one long
outage exhaust the budget and park the backend behind a manual hold.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from unittest.mock import Mock

import cohort_backend_supervisor as sup
import cohort_supervisor_runtime as runtime
from cohort_supervisor_restart_policy import (
    EXIT_DEGRADED_BLINDNESS,
    charges_restart_budget,
    decide_restart,
)
from cohort_supervisor_state import RestartJournal
from cohort_supervisor_venue_wait import (
    MARKER_FRESH_SECONDS,
    VENUE_WAIT_MARKER,
    backend_venue_wait,
)
from test_cohort_backend_supervisor import FAST, _events, _paths, _run

from hypervector.live import cohort_venue_start_probe

POLICY = sup.RestartPolicy(
    maximum_restarts=2,
    window_seconds=1_000.0,
    initial_backoff_seconds=10.0,
    maximum_backoff_seconds=100.0,
)


def test_blindness_exit_restarts_even_with_an_exhausted_crash_budget() -> None:
    decision = decide_restart(
        EXIT_DEGRADED_BLINDNESS,
        stop_file_present=False,
        restart_times=[1.0, 2.0, 3.0, 4.0],
        policy=POLICY,
        now=5.0,
    )

    assert (decision.action, decision.reason) == (
        "restart",
        "degraded_blindness_uncharged",
    )
    assert decision.delay_seconds == POLICY.initial_backoff_seconds
    assert charges_restart_budget(EXIT_DEGRADED_BLINDNESS) is False
    assert all(charges_restart_budget(code) for code in (1, -9, -15, 3))


def test_a_stop_file_still_holds_after_a_blindness_exit() -> None:
    decision = decide_restart(
        EXIT_DEGRADED_BLINDNESS,
        stop_file_present=True,
        restart_times=[],
        policy=POLICY,
        now=5.0,
    )

    assert (decision.action, decision.reason) == ("hold", "operator_stop_file_present")


def test_uncharged_reservation_records_the_session_but_not_a_launch(
    tmp_path: Path,
) -> None:
    journal = RestartJournal(tmp_path / "events.jsonl", ["backend"])
    assert journal.reserve(100.0, POLICY)
    assert journal.reserve(101.0, POLICY)
    assert journal.reserve(102.0, POLICY)

    # The crash budget is spent, yet the blindness relaunch proceeds uncharged.
    assert journal.reserve(103.0, POLICY, charged=False)
    payload = json.loads(journal.path.read_text())
    assert payload["launch_times"] == [100.0, 101.0, 102.0]
    assert payload["session_active"] is True
    assert journal.hold_reason is None

    # A crash after it is still refused by the untouched budget.
    assert not journal.reserve(104.0, POLICY)
    assert journal.hold_reason == "restart_budget_exhausted"


def test_uncharged_reservation_keeps_every_other_hold(tmp_path: Path) -> None:
    journal = RestartJournal(tmp_path / "events.jsonl", ["backend"])
    journal.hold("operator_stop_file_present")
    assert not journal.reserve(100.0, POLICY, charged=False)

    clock = RestartJournal(tmp_path / "other.jsonl", ["backend"])
    assert clock.reserve(100.0, POLICY)
    assert not clock.reserve(99.0, POLICY, charged=False)
    assert clock.hold_reason == "restart_clock_moved_backwards"


def test_acceptance_repeated_blindness_exits_never_give_up(tmp_path: Path) -> None:
    """Four blindness exits in a row relaunch four times on a two-restart budget."""
    code, paths, recorder = _run(tmp_path, "exit4,exit4,exit4,exit4,exit0")

    events = _events(paths)
    decisions = [e["reason"] for e in events if e["event"] == "restart_decision"]
    assert code == 0
    assert [e["event"] for e in events].count("backend_launched") == 5
    assert decisions == ["degraded_blindness_uncharged"] * 4 + [
        "clean_exit_operator_stop_or_bounded_run"
    ]
    journal = json.loads((tmp_path / "events_restart_state.json").read_text())
    assert len(journal["launch_times"]) == 1
    assert ("HYPERVECTOR BACKEND RESTARTING", "degraded_blindness_uncharged") in (
        recorder.sent
    )


def test_acceptance_crash_budget_is_intact_after_a_blindness_exit(
    tmp_path: Path,
) -> None:
    """The uncharged relaunch is extra; crashes still get exactly their budget."""
    code, paths, recorder = _run(tmp_path, "exit4,exit1")

    events = _events(paths)
    assert code == 1
    assert [e["event"] for e in events].count("backend_launched") == (
        1 + 1 + FAST.maximum_restarts
    )
    assert events[-1]["action"] == "give_up"
    assert recorder.sent[-1][0] == "HYPERVECTOR SUPERVISOR GAVE UP"


# --------------------------------------------------------------------------- #
# a backend waiting for the venue
# --------------------------------------------------------------------------- #


def _marker(
    paths: sup.SupervisorPaths, pid: int, updated: float, attempts: int = 3
) -> Path:
    path = paths.process_lock.with_name(VENUE_WAIT_MARKER)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pid": pid,
                "waiting_since_utc": "2026-09-24T16:00:00+00:00",
                "updated_at_utc": datetime.fromtimestamp(updated, UTC).isoformat(),
                "attempts": attempts,
                "reason": "transport_connection_retry_exhausted",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_marker_name_matches_the_backend_probe() -> None:
    assert VENUE_WAIT_MARKER == cohort_venue_start_probe.VENUE_WAIT_MARKER


def test_only_this_backends_fresh_marker_reads_as_waiting(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    now = 1_790_000_000.0
    _marker(paths, 4242, now - 10.0)

    wait = backend_venue_wait(paths.process_lock, 4242, now)
    assert wait is not None and wait.attempts == 3
    assert wait.reason == "transport_connection_retry_exhausted"
    assert backend_venue_wait(paths.process_lock, 999, now) is None
    assert (
        backend_venue_wait(paths.process_lock, 4242, now + MARKER_FRESH_SECONDS + 11.0)
        is None
    )

    paths.process_lock.with_name(VENUE_WAIT_MARKER).write_text("{broken")
    assert backend_venue_wait(paths.process_lock, 4242, now) is None
    paths.process_lock.with_name(VENUE_WAIT_MARKER).unlink()
    assert backend_venue_wait(paths.process_lock, 4242, now) is None


class _Observer:
    def __init__(self) -> None:
        self.problems: list[tuple[float, tuple[str, ...]]] = []
        self.emitted: list[tuple[str, str]] = []

    def observe(self, report: sup.HealthReport, now: float) -> bool:
        self.problems.append((now, report.problems))
        return False

    def emit(self, title: str, body: str, record: object, now: float) -> None:
        self.emitted.append((title, body))


def test_a_waiting_backend_is_announced_and_not_reported_stale(
    tmp_path: Path,
) -> None:
    """Past the startup grace, a waiting backend is not a stale heartbeat.

    Its grace restarts when the wait ends, because the ledger replay and the
    engine starts it still has ahead of it only begin then.
    """
    paths = _paths(tmp_path)
    policy = sup.RestartPolicy(startup_grace_seconds=100.0)
    clock = {"now": 1_790_000_000.0}
    started = clock["now"]
    child = Mock(pid=4242)
    polls = iter([None] * 16 + [0])
    child.poll.side_effect = lambda: next(polls)
    observer = _Observer()

    def sleep(seconds: float) -> None:
        clock["now"] += seconds
        elapsed = clock["now"] - started
        marker = paths.process_lock.with_name(VENUE_WAIT_MARKER)
        if elapsed < 150.0:
            _marker(paths, 4242, clock["now"])
        else:
            marker.unlink(missing_ok=True)

    _marker(paths, 4242, clock["now"])
    code = runtime._watch_child(
        child,
        paths,
        sup.HealthThresholds(),
        policy,
        observer,  # type: ignore[arg-type]
        runtime._StopFlag(),
        sup.SupervisorRuntime(
            now=lambda: clock["now"],
            sleep=sleep,
            is_backend=lambda _pid: True,
            deadman=lambda _url: None,
        ),
        interval=20.0,
        started=started,
        deadman_url=None,
    )

    assert code == 0
    assert observer.emitted == [
        ("HYPERVECTOR BACKEND WAITING FOR VENUE", "backend_waiting_for_venue")
    ]
    stale = [
        now - started
        for now, problems in observer.problems
        if "backend_heartbeat_stale" in problems
    ]
    # The wait was last seen at 140 s, so the 100 s grace runs to 240 s.
    assert stale and min(stale) >= 240.0
    names = [event["event"] for event in _events(paths)]
    assert names.count("backend_waiting_for_venue") == 1
