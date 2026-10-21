"""Supervisor policy, health probes and the induced-kill acceptance test.

The acceptance tests drive a real child process through a real SIGKILL. The child
is a stub that honours the backend's observable contract (singleton lock PID,
appended ledger heartbeat, exit codes) so nothing here touches the live cohort,
its ledgers, or the shared public-request budget.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import UTC, datetime
import signal
import sys
import textwrap
import threading
import time

import pytest

import cohort_backend_supervisor as sup


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _paths(root: Path) -> sup.SupervisorPaths:
    return sup.SupervisorPaths(
        ledger=root / "decisions.jsonl",
        process_lock=root / "process.lock",
        stop_file=root / "STOP",
        checkpoint=root / "latest_checkpoint.json",
        roster=root / "hip3_roster_latest.json",
        alerts=root / "alerts.jsonl",
        events=root / "events.jsonl",
        child_log=root / "child.log",
    )


def _write_healthy_files(paths: sup.SupervisorPaths, *, fee_bps: float = 0.864) -> None:
    paths.ledger.write_text("{}\n", encoding="utf-8")
    paths.process_lock.write_text("4242", encoding="utf-8")
    now_ms = time.time() * 1000.0
    notional = 500.0
    paths.checkpoint.write_text(
        json.dumps(
            {
                "generated_at_utc": datetime.now(UTC).isoformat(),
                "audit": {
                    "run": {"executable_provider_symbols": ["test_channel_provider|xyz:CCC"]},
                    "execution": {
                        "fill_details": [
                            {
                                "symbol": "xyz:CCC",
                                "price": 100.0,
                                "size": 5.0,
                                "fee_usd": notional * fee_bps / 10_000.0,
                                "venue_timestamp_ms": now_ms,
                            },
                            {
                                "symbol": "BTC",
                                "price": 100.0,
                                "size": 5.0,
                                "fee_usd": notional * 4.32 / 10_000.0,
                                "venue_timestamp_ms": now_ms,
                            },
                        ]
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    paths.roster.write_text(
        json.dumps(
            {
                "status": "available",
                "lifecycle": "running",
                "observed_at_utc": datetime.now(UTC).isoformat(),
                "active_symbols": ["xyz:CCC", "xyz:DDD"],
                "markets": [
                    {
                        "symbol": "xyz:CCC",
                        "venue": {
                            "growth_mode": True,
                            "deployer_fee_scale": 1.0,
                            "effective_fee_status": "resolved",
                        },
                    },
                    {
                        "symbol": "xyz:DDD",
                        "venue": {
                            "growth_mode": None,
                            "deployer_fee_scale": 1.0,
                            "effective_fee_status": "unresolved_growth_mode",
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


# Supervision reads the boot identity once at start. No test runs sysctl or
# reads the host's shutdown history.
FAKE_HOST: dict[str, object] = {
    "boot_identity": lambda: sup.BootIdentity(
        "00000000-0000-4000-8000-000000000001", 1_000.0
    ),
    "previous_shutdown": lambda _boot_time: None,
}


class _Recorder:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, title: str, body: str, record: dict[str, object]) -> None:
        self.sent.append((title, body))


def _events(paths: sup.SupervisorPaths) -> list[dict[str, object]]:
    if not paths.events.exists():
        return []
    return [json.loads(line) for line in paths.events.read_text().splitlines() if line]


# --------------------------------------------------------------------------- #
# restart policy
# --------------------------------------------------------------------------- #


POLICY = sup.RestartPolicy(
    maximum_restarts=3,
    window_seconds=1_000.0,
    initial_backoff_seconds=10.0,
    maximum_backoff_seconds=35.0,
)


def test_clean_exit_is_an_operator_stop_and_is_never_restarted() -> None:
    decision = sup.decide_restart(
        0, stop_file_present=False, restart_times=(), policy=POLICY, now=0.0
    )
    assert decision.action == "stop"


def test_stop_file_holds_even_after_a_crash() -> None:
    decision = sup.decide_restart(
        -9, stop_file_present=True, restart_times=(), policy=POLICY, now=0.0
    )
    assert (decision.action, decision.reason) == ("hold", "operator_stop_file_present")


def test_a_refused_live_start_is_held_not_looped() -> None:
    decision = sup.decide_restart(
        2, stop_file_present=False, restart_times=(), policy=POLICY, now=0.0
    )
    assert (decision.action, decision.reason) == (
        "hold",
        "live_start_refused_fail_closed",
    )


@pytest.mark.parametrize("exit_code", [1, -9, -15, 137])
def test_unexpected_exits_restart_with_exponential_backoff(exit_code: int) -> None:
    first = sup.decide_restart(
        exit_code, stop_file_present=False, restart_times=(), policy=POLICY, now=100.0
    )
    third = sup.decide_restart(
        exit_code,
        stop_file_present=False,
        restart_times=(50.0, 90.0),
        policy=POLICY,
        now=100.0,
    )
    assert (first.action, first.delay_seconds) == ("restart", 10.0)
    assert (third.action, third.delay_seconds) == ("restart", 35.0)  # 40 capped at 35


def test_restart_budget_is_exhausted_then_recovers_after_the_window() -> None:
    crashes = (100.0, 200.0, 300.0)
    exhausted = sup.decide_restart(
        1, stop_file_present=False, restart_times=crashes, policy=POLICY, now=400.0
    )
    later = sup.decide_restart(
        1, stop_file_present=False, restart_times=crashes, policy=POLICY, now=1_250.0
    )
    assert exhausted.action == "give_up"
    assert later.action == "restart"  # 100.0 and 200.0 have left the rolling window


# --------------------------------------------------------------------------- #
# health probes
# --------------------------------------------------------------------------- #


def test_a_fully_healthy_system_reports_no_problems(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    report = sup.evaluate_health(
        paths, sup.HealthThresholds(), now=time.time(), is_backend=lambda _pid: True
    )
    assert report.healthy
    assert report.backend_pid == 4242
    assert report.maximum_hip3_fill_fee_bps == pytest.approx(0.864)


def test_core_perp_fees_never_trip_the_hip3_fee_probe(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    report = sup.evaluate_health(
        paths, sup.HealthThresholds(), now=time.time(), is_backend=lambda _pid: True
    )
    assert "hip3_fill_fee_above_threshold" not in report.problems


def test_every_failure_is_named(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_healthy_files(paths, fee_bps=8.64)
    roster = json.loads(paths.roster.read_text())
    roster["markets"][0]["venue"]["growth_mode"] = False
    paths.roster.write_text(json.dumps(roster))
    stale = time.time() - 5_000.0
    for path in (paths.ledger, paths.checkpoint, paths.roster):
        os.utime(path, (stale, stale))
    report = sup.evaluate_health(
        paths,
        sup.HealthThresholds(fee_lookback_hours=24.0),
        now=time.time(),
        is_backend=lambda _pid: False,
    )
    assert set(report.problems) == {
        "backend_process_absent",
        "backend_heartbeat_stale",
        "checkpoint_stale",
        "roster_observer_stale",
        "hip3_fee_regime_changed",
        "hip3_fill_fee_above_threshold",
    }
    assert report.hip3_fee_regime == {"xyz:CCC": "growth_mode=False"}


def test_unresolved_growth_mode_is_not_reported_as_a_regime_change(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    assert sup.hip3_fee_regime(paths.roster) == {}


def test_missing_files_are_stale_not_silently_healthy(tmp_path: Path) -> None:
    report = sup.evaluate_health(
        _paths(tmp_path),
        sup.HealthThresholds(),
        now=time.time(),
        is_backend=lambda _pid: True,
    )
    assert {
        "backend_process_absent",
        "backend_heartbeat_stale",
        "checkpoint_stale",
        "roster_observer_stale",
    } <= set(report.problems)


def test_heartbeat_is_not_required_during_startup_grace(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    stale = time.time() - 5_000.0
    os.utime(paths.ledger, (stale, stale))
    report = sup.evaluate_health(
        paths,
        sup.HealthThresholds(),
        now=time.time(),
        is_backend=lambda _pid: True,
        heartbeat_required=False,
    )
    assert "backend_heartbeat_stale" not in report.problems


def test_a_recycled_pid_is_not_mistaken_for_the_backend() -> None:
    assert sup.process_is_backend(os.getpid()) is False


# --------------------------------------------------------------------------- #
# alerting
# --------------------------------------------------------------------------- #


def _report(*problems: str) -> sup.HealthReport:
    return sup.HealthReport(
        checked_at_utc="t",
        backend_pid=1,
        backend_alive=True,
        ledger_age_seconds=1.0,
        checkpoint_age_seconds=1.0,
        roster_age_seconds=1.0,
        stop_file_present=False,
        maximum_hip3_fill_fee_bps=None,
        problems=tuple(problems),
    )


def test_alerts_fire_on_change_remind_while_unhealthy_and_announce_recovery() -> None:
    recorder = _Recorder()
    alerter = sup.Alerter([recorder], reminder_seconds=100.0)
    assert alerter.observe(_report(), 0.0) is False  # first healthy look is silent
    assert alerter.observe(_report("checkpoint_stale"), 10.0) is True
    assert (
        alerter.observe(_report("checkpoint_stale"), 50.0) is False
    )  # unchanged, no spam
    assert alerter.observe(_report("checkpoint_stale"), 120.0) is True  # reminder
    assert (
        alerter.observe(_report("checkpoint_stale", "backend_heartbeat_stale"), 121.0)
        is True
    )
    assert alerter.observe(_report(), 130.0) is True
    assert [title for title, _body in recorder.sent] == [
        "Hypervector notice",  # informational: stays off the push channel
        "Hypervector notice",
        "HYPERVECTOR BACKEND ALERT",
        "Hypervector recovered",
    ]


def test_alert_journal_is_append_only_jsonl(tmp_path: Path) -> None:
    sink = sup.JsonlSink(tmp_path / "nested" / "alerts.jsonl")
    sink.send("a", "b", {"k": 1})
    sink.send("c", "d", {"k": 2})
    rows = [
        json.loads(x)
        for x in (tmp_path / "nested" / "alerts.jsonl").read_text().splitlines()
    ]
    assert [row["k"] for row in rows] == [1, 2]


# --------------------------------------------------------------------------- #
# induced-kill acceptance
# --------------------------------------------------------------------------- #


STUB = textwrap.dedent(
    """
    import os, sys, time
    root, plan = sys.argv[1], sys.argv[2].split(",")
    counter = os.path.join(root, "launches")
    n = int(open(counter).read()) if os.path.exists(counter) else 0
    open(counter, "w").write(str(n + 1))
    open(os.path.join(root, "process.lock"), "w").write(str(os.getpid()))
    step = plan[min(n, len(plan) - 1)]
    deadline = time.time() + 30.0
    while time.time() < deadline:
        with open(os.path.join(root, "decisions.jsonl"), "a") as handle:
            handle.write("{}\\n")
        if step.startswith("exit"):
            sys.exit(int(step[4:]))
        time.sleep(0.02)
    """
)

FAST = sup.RestartPolicy(
    maximum_restarts=2,
    window_seconds=600.0,
    initial_backoff_seconds=0.05,
    maximum_backoff_seconds=0.05,
    startup_grace_seconds=600.0,
)


def _stub_command(tmp_path: Path, plan: str) -> list[str]:
    script = tmp_path / "stub_backend.py"
    script.write_text(STUB, encoding="utf-8")
    return [sys.executable, str(script), str(tmp_path), plan]


def _run(
    tmp_path: Path, plan: str, **kwargs: object
) -> tuple[int, sup.SupervisorPaths, _Recorder]:
    paths = _paths(tmp_path)
    recorder = _Recorder()
    code = sup.supervise(
        _stub_command(tmp_path, plan),
        paths,
        sup.HealthThresholds(),
        FAST,
        sup.Alerter([recorder]),
        interval=0.02,
        working_directory=tmp_path,
        runtime=sup.SupervisorRuntime(
            is_backend=lambda _pid: False, deadman=lambda _url: None, **FAKE_HOST
        ),
        **kwargs,
    )
    return code, paths, recorder


def test_acceptance_induced_kill_is_restarted_then_operator_stop_is_final(
    tmp_path: Path,
) -> None:
    """SIGKILL the backend; the supervisor relaunches it; a clean exit then stops it."""
    lock = tmp_path / "process.lock"

    def kill_first_launch() -> None:
        deadline = time.time() + 10.0
        while time.time() < deadline and not lock.exists():
            time.sleep(0.01)
        os.kill(int(lock.read_text()), signal.SIGKILL)

    killer = threading.Thread(target=kill_first_launch)
    killer.start()
    code, paths, recorder = _run(tmp_path, "run,exit0")
    killer.join()

    events = _events(paths)
    names = [event["event"] for event in events]
    exits = [
        event["exit_code"] for event in events if event["event"] == "backend_exited"
    ]
    launched = [
        event["pid"] for event in events if event["event"] == "backend_launched"
    ]
    assert code == 0
    assert names.count("backend_launched") == 2
    assert exits == [-signal.SIGKILL, 0]
    assert launched[0] != launched[1]
    assert [e["action"] for e in events if e["event"] == "restart_decision"] == [
        "restart",
        "stop",
    ]
    assert any(title == "HYPERVECTOR BACKEND RESTARTING" for title, _ in recorder.sent)
    assert "supervisor launch 2" in paths.child_log.read_text()


def test_acceptance_repeated_crashes_exhaust_the_budget_and_give_up(
    tmp_path: Path,
) -> None:
    code, paths, recorder = _run(tmp_path, "exit1")
    events = _events(paths)
    assert code == 1
    assert [e["event"] for e in events].count(
        "backend_launched"
    ) == FAST.maximum_restarts + 1
    assert events[-1]["action"] == "give_up"
    assert recorder.sent[-1][0] == "HYPERVECTOR SUPERVISOR GAVE UP"


def test_acceptance_refused_start_holds_without_relaunching(tmp_path: Path) -> None:
    stop = sup._StopFlag()

    def release_hold() -> None:
        events_path = tmp_path / "events.jsonl"
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if events_path.exists() and '"holding"' in events_path.read_text():
                break
            time.sleep(0.01)
        stop.requested = True

    releaser = threading.Thread(target=release_hold)
    releaser.start()
    code, paths, recorder = _run(tmp_path, "exit2", stop=stop)
    releaser.join()
    names = [event["event"] for event in _events(paths)]
    assert code == 0
    assert names.count("backend_launched") == 1
    assert "holding" in names
    assert (
        "HYPERVECTOR BACKEND HELD",
        "live_start_refused_fail_closed",
    ) in recorder.sent


def test_acceptance_stop_file_blocks_restart_after_a_crash(tmp_path: Path) -> None:
    (tmp_path / "STOP").write_text("operator", encoding="utf-8")
    stop = sup._StopFlag()
    threading.Timer(1.0, lambda: setattr(stop, "requested", True)).start()
    code, paths, _recorder = _run(tmp_path, "exit1", stop=stop)
    decisions = [e for e in _events(paths) if e["event"] == "restart_decision"]
    assert code == 0
    assert [d["reason"] for d in decisions] == ["operator_stop_file_present"]


def test_a_second_backend_is_refused_and_then_monitored(tmp_path: Path) -> None:
    """A competing owner must be alerted and watched, never bounced into KeepAlive.

    Returning a nonzero code here made launchd relaunch every ThrottleInterval into
    the same refusal, so an orphaned armed backend ran with no health polling and
    no alerts for as long as it survived.
    """
    paths = _paths(tmp_path)
    paths.process_lock.write_text("4242", encoding="utf-8")
    recorder = _Recorder()
    stop = sup._StopFlag()
    threading.Timer(1.0, lambda: setattr(stop, "requested", True)).start()
    code = sup.supervise(
        _stub_command(tmp_path, "exit0"),
        paths,
        sup.HealthThresholds(),
        FAST,
        sup.Alerter([recorder]),
        interval=0.02,
        working_directory=tmp_path,
        stop=stop,
        runtime=sup.SupervisorRuntime(
            is_backend=lambda _pid: True, deadman=lambda _url: None, **FAKE_HOST
        ),
    )
    names = [event["event"] for event in _events(paths)]
    assert code == 0
    assert names[:2] == ["refused_backend_already_running", "holding"]
    assert "backend_launched" not in names
    assert any("UNSUPERVISED" in title for title, _body in recorder.sent)


def test_mid_session_fault_holds_instead_of_reporting_a_start_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An OSError raised while supervising must not read as "refused to start".

    The old handler spanned the whole session, so a mid-session write error
    returned EXIT_START_REFUSED and left the armed child orphaned.
    """
    paths = _paths(tmp_path)
    recorder = _Recorder()
    stop = sup._StopFlag()

    def explode(self: object, now: float, policy: object) -> bool:
        raise OSError("journal volume disappeared")

    monkeypatch.setattr(sup.RestartJournal, "reserve", explode)

    def sleep(_seconds: float) -> None:
        stop.requested = True

    code = sup.supervise(
        _stub_command(tmp_path, "exit0"),
        paths,
        sup.HealthThresholds(),
        FAST,
        sup.Alerter([recorder]),
        interval=0.02,
        working_directory=tmp_path,
        stop=stop,
        runtime=sup.SupervisorRuntime(
            sleep=sleep,
            is_backend=lambda _pid: False,
            deadman=lambda _url: None,
            **FAKE_HOST,
        ),
    )
    names = [event["event"] for event in _events(paths)]

    assert code == 0
    assert "supervisor_faulted" in names
    assert "supervisor_start_refused" not in names
    assert any("FAULTED" in title for title, _body in recorder.sent)


@pytest.mark.parametrize(("policy", "expected_launches"), [("hold", 0), ("restart", 1)])
def test_adopted_backend_exit_follows_the_explicit_policy(
    tmp_path: Path, policy: str, expected_launches: int
) -> None:
    paths = _paths(tmp_path)
    paths.process_lock.write_text("4242", encoding="utf-8")
    alive = iter([True, True, False])
    stop = sup._StopFlag()
    if policy == "hold":
        threading.Timer(1.0, lambda: setattr(stop, "requested", True)).start()
    code = sup.supervise(
        _stub_command(tmp_path, "exit0"),
        paths,
        sup.HealthThresholds(),
        FAST,
        sup.Alerter([_Recorder()]),
        interval=0.02,
        working_directory=tmp_path,
        adopt=True,
        adopted_exit_policy=policy,
        stop=stop,
        runtime=sup.SupervisorRuntime(
            is_backend=lambda _pid: next(alive, False),
            deadman=lambda _url: None,
            **FAKE_HOST,
        ),
    )
    names = [event["event"] for event in _events(paths)]
    assert code == 0
    assert names[:2] == ["adopted_running_backend", "adopted_backend_ended"]
    assert names.count("backend_launched") == expected_launches


# --------------------------------------------------------------------------- #
# launchd and isolation
# --------------------------------------------------------------------------- #


def test_launchd_agent_relaunches_a_crash_but_respects_an_operator_stop() -> None:
    import plistlib

    plist = plistlib.loads(
        sup.launchd_plist(
            "watch", ["watch", "--interval", "30"], python=Path("/usr/bin/python3")
        )
    )
    assert plist["KeepAlive"] == {"SuccessfulExit": False}
    assert plist["RunAtLoad"] is True
    assert plist["ProgramArguments"][2:] == ["watch", "--interval", "30"]


def test_supervisor_never_imports_the_package_it_supervises() -> None:
    source = Path(sup.__file__).read_text(encoding="utf-8")
    import ast

    imports = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    names = [
        name.name
        for node in imports
        if isinstance(node, ast.Import)
        for name in node.names
    ]
    names += [node.module or "" for node in imports if isinstance(node, ast.ImportFrom)]
    assert not any(
        name == "hypervector" or name.startswith("hypervector.") for name in names
    )
    assert "PRIVATE_KEY" not in source
