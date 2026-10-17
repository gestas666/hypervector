"""A host restart must not end in a silent, durable hold; an operator stop still must.

Reproduces 2026-09-26: the shutdown's SIGTERM latched ``operator_signal_stop``,
re-latched as ``operator_stop_grace_expired``; RunAtLoad started a new
supervisor 57 s after boot, which read the hold, gave up, exited 0 without an
alert, and launchd never relaunched it. The book stayed dark 29 minutes.

No test here runs sysctl, launchctl or the host's wtmpx reader: the boot
identity and the previous shutdown are injected.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import threading
import time

import pytest

import cohort_backend_supervisor as sup
import cohort_supervisor_alerts as alerts
import cohort_supervisor_host as host
from cohort_supervisor_runtime import RELAUNCHING_AFTER_HOST_RESTART_TITLE
from cohort_supervisor_host import BootIdentity
from cohort_supervisor_restart_policy import (
    HOST_RESTART_HOLD_WINDOW_SECONDS,
    decide_host_restart_resume,
)
from cohort_supervisor_state import RestartJournal
from test_cohort_backend_supervisor import (
    FAST,
    _Recorder,
    _events,
    _paths,
    _stub_command,
)

OLD_SESSION = "11111111-2222-4333-8444-555555555555"
NEW_SESSION = "5A70DD99-9026-4AF1-A0A1-7B03B65D0732"
# 2026-09-26, from this host's wtmpx and supervisor journal.
SHUTDOWN = 1_790_462_947.103214  # 22:49:07.10Z, SHUTDOWN_TIME record
FINAL_LATCH = 1_790_462_980.068  # 22:49:40.07Z, grace expired, child exited
BOOT = 1_790_463_001.331787  # 22:50:01.33Z, kern.boottime
NEW_BOOT = BootIdentity(NEW_SESSION, BOOT)


def _no_shutdown_reader(_boot_time: float) -> float | None:
    raise AssertionError("the shutdown history must not be read for this case")


def _journal(
    tmp_path: Path, *, session: str | None = OLD_SESSION, clock: float = FINAL_LATCH
) -> RestartJournal:
    return RestartJournal(
        tmp_path / "events.jsonl",
        ["backend"],
        boot_session=session,
        clock=lambda: clock,
    )


def _decide(
    journal: RestartJournal,
    *,
    boot: BootIdentity = NEW_BOOT,
    shutdown: float | None = SHUTDOWN,
    stop_file_present: bool = False,
    backend_alive: bool = False,
    free_disk_gib: float | None = 50.0,
):
    return decide_host_restart_resume(
        journal,
        boot,
        previous_shutdown=lambda _boot_time: shutdown,
        stop_file_present=stop_file_present,
        backend_alive=backend_alive,
        free_disk_gib=free_disk_gib,
        minimum_free_disk_gib=10.0,
    )


def _state(tmp_path: Path) -> dict[str, object]:
    return json.loads((tmp_path / "events_restart_state.json").read_text())


# --------------------------------------------------------------------------- #
# journal stamps
# --------------------------------------------------------------------------- #


def test_every_hold_and_launch_is_stamped_with_its_boot_session(tmp_path: Path) -> None:
    journal = _journal(tmp_path, clock=4_000.0)
    assert journal.reserve(3_000.0, FAST)
    assert _state(tmp_path)["launch_boot_session"] == OLD_SESSION
    journal.hold("operator_signal_stop")
    state = _state(tmp_path)
    assert state["held_at_epoch"] == 4_000.0
    assert state["held_boot_session"] == OLD_SESSION
    assert state["launch_boot_session"] == OLD_SESSION
    reloaded = _journal(tmp_path, session=NEW_SESSION)
    assert (reloaded.held_at_epoch, reloaded.held_boot_session) == (
        4_000.0,
        OLD_SESSION,
    )


def test_journal_without_stamps_loads_and_stays_unstamped(tmp_path: Path) -> None:
    """The 2026-09-26 journal shape loads; old code ignores the new keys too."""
    (tmp_path / "events_restart_state.json").write_text(
        json.dumps(
            {
                "command_sha256": _journal(tmp_path).command_sha256,
                "hold_reason": "operator_stop_grace_expired",
                "launch_times": [1790318111.1002219],
                "schema_version": 1,
                "session_active": False,
            }
        )
    )
    journal = _journal(tmp_path, session=NEW_SESSION)
    assert journal.held_at_epoch is None and journal.held_boot_session is None
    assert _decide(journal).reason == "hold_not_stamped_with_boot_session"


@pytest.mark.parametrize(
    "update",
    [
        {"held_at_epoch": "yesterday"},
        {"held_at_epoch": -1.0},
        {"held_at_epoch": True},
        {"held_boot_session": 7},
        {"held_boot_session": ""},
        {"launch_boot_session": ["x"]},
        {"launch_boot_session": "x" * 65},
    ],
)
def test_malformed_stamps_are_refused(
    tmp_path: Path, update: dict[str, object]
) -> None:
    journal = _journal(tmp_path)
    journal.hold("operator_signal_stop")
    journal.path.write_text(json.dumps({**_state(tmp_path), **update}))
    with pytest.raises(ValueError):
        _journal(tmp_path)


def test_release_is_durable_and_an_unwritable_journal_keeps_the_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _journal(tmp_path).hold("operator_signal_stop")
    journal = _journal(tmp_path, session=NEW_SESSION)
    monkeypatch.setattr(journal, "_save", lambda: False)
    assert journal.release_after_host_restart() is False
    assert journal.hold_reason == "operator_signal_stop"
    assert journal.held_boot_session == OLD_SESSION
    monkeypatch.undo()
    assert journal.release_after_host_restart() is True
    state = _state(tmp_path)
    assert state["hold_reason"] is None and state["held_at_epoch"] is None
    assert state["session_active"] is False


# --------------------------------------------------------------------------- #
# the resume decision
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "reason", ["operator_signal_stop", "operator_stop_grace_expired"]
)
def test_the_2026_09_26_signal_hold_resumes(tmp_path: Path, reason: str) -> None:
    """Latched 33 s after the shutdown record: a strict "before" test would hold."""
    _journal(tmp_path).hold(reason)
    decision = _decide(_journal(tmp_path, session=NEW_SESSION))
    assert (decision.resume, decision.reason) == (
        True,
        "latched_by_previous_boot_shutdown",
    )
    assert decision.evidence["hold_after_shutdown_seconds"] == pytest.approx(32.965)
    assert decision.evidence["previous_shutdown_epoch"] == SHUTDOWN


def test_a_signal_hold_latched_in_this_boot_is_an_operator_stop(tmp_path: Path) -> None:
    """``launchctl bootout`` or kill, then bootstrap, without a reboot."""
    _journal(tmp_path, session=NEW_SESSION, clock=BOOT + 600.0).hold(
        "operator_signal_stop"
    )
    decision = decide_host_restart_resume(
        _journal(tmp_path, session=NEW_SESSION),
        BootIdentity(NEW_SESSION, BOOT),
        previous_shutdown=_no_shutdown_reader,
        stop_file_present=False,
        backend_alive=False,
        free_disk_gib=50.0,
        minimum_free_disk_gib=10.0,
    )
    assert (decision.resume, decision.reason) == (False, "hold_latched_in_this_boot")


# The 2026-09-13 update install: shutdown to boot took 23 minutes.
UPDATE_BOOT = BootIdentity(NEW_SESSION, SHUTDOWN + 23 * 60.0)


@pytest.mark.parametrize(
    ("held_at", "expected"),
    [
        (SHUTDOWN - 3_600.0, "hold_outside_shutdown_window"),  # bootout, reboot later
        (
            SHUTDOWN - HOST_RESTART_HOLD_WINDOW_SECONDS - 1.0,
            "hold_outside_shutdown_window",
        ),
        (
            SHUTDOWN + HOST_RESTART_HOLD_WINDOW_SECONDS + 1.0,
            "hold_outside_shutdown_window",
        ),
        (
            SHUTDOWN - HOST_RESTART_HOLD_WINDOW_SECONDS + 1.0,
            "latched_by_previous_boot_shutdown",
        ),
        (
            SHUTDOWN + HOST_RESTART_HOLD_WINDOW_SECONDS - 1.0,
            "latched_by_previous_boot_shutdown",
        ),
        (UPDATE_BOOT.boot_time_epoch + 1.0, "hold_not_before_this_boot"),  # type: ignore[operator]
    ],
)
def test_the_window_is_anchored_to_the_previous_shutdown(
    tmp_path: Path, held_at: float, expected: str
) -> None:
    """Not to the new boot: update installs took 23 and 87 min to boot here."""
    _journal(tmp_path, clock=held_at).hold("operator_signal_stop")
    decision = _decide(_journal(tmp_path, session=NEW_SESSION), boot=UPDATE_BOOT)
    assert decision.reason == expected


def test_a_long_update_install_between_shutdown_and_boot_still_resumes(
    tmp_path: Path,
) -> None:
    _journal(tmp_path, clock=SHUTDOWN + 20.0).hold("operator_signal_stop")
    late_boot = BootIdentity(NEW_SESSION, SHUTDOWN + 87 * 60.0)
    assert _decide(_journal(tmp_path, session=NEW_SESSION), boot=late_boot).resume


def test_a_boot_without_a_shutdown_record_keeps_a_signal_hold(tmp_path: Path) -> None:
    _journal(tmp_path).hold("operator_signal_stop")
    decision = _decide(_journal(tmp_path, session=NEW_SESSION), shutdown=None)
    assert (decision.resume, decision.reason) == (False, "previous_shutdown_unknown")


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"stop_file_present": True}, "operator_stop_file_present"),
        ({"backend_alive": True}, "backend_process_alive"),
        ({"free_disk_gib": 9.9}, "insufficient_free_disk"),
        ({"free_disk_gib": None}, "insufficient_free_disk"),
        ({"boot": BootIdentity(None, BOOT)}, "boot_identity_unknown"),
        ({"boot": BootIdentity(NEW_SESSION, None)}, "boot_identity_unknown"),
    ],
)
def test_every_precondition_keeps_the_hold_before_reading_the_shutdown_history(
    tmp_path: Path, overrides: dict[str, object], expected: str
) -> None:
    _journal(tmp_path).hold("operator_signal_stop")
    arguments: dict[str, object] = {
        "boot": NEW_BOOT,
        "stop_file_present": False,
        "backend_alive": False,
        "free_disk_gib": 50.0,
        **overrides,
    }
    decision = decide_host_restart_resume(
        _journal(tmp_path, session=NEW_SESSION),
        arguments.pop("boot"),  # type: ignore[arg-type]
        previous_shutdown=_no_shutdown_reader,
        minimum_free_disk_gib=10.0,
        **arguments,  # type: ignore[arg-type]
    )
    assert (decision.resume, decision.reason) == (False, expected)


@pytest.mark.parametrize(
    "reason",
    [
        "clean_exit_operator_stop_or_bounded_run",
        "operator_stop_file_present",
        "live_start_refused_fail_closed",
        "restart_budget_exhausted",
        "insufficient_free_disk",
        "restart_clock_moved_backwards",
        "restart_journal_unwritable",
        "adopted_exit_status_unobservable",
        "supervisor_faulted:OSError",
    ],
)
def test_no_other_hold_is_ever_released(tmp_path: Path, reason: str) -> None:
    _journal(tmp_path, clock=SHUTDOWN + 5.0).hold(reason)
    decision = _decide(_journal(tmp_path, session=NEW_SESSION))
    assert (decision.resume, decision.reason) == (False, "hold_not_host_restart_class")


def test_an_unresolved_session_of_the_previous_boot_resumes(tmp_path: Path) -> None:
    """Power loss, panic, or a SIGKILL: the session never recorded its end."""
    assert _journal(tmp_path).reserve(SHUTDOWN - 86_400.0, FAST)
    journal = _journal(tmp_path, session=NEW_SESSION)
    assert journal.hold_reason == "previous_supervisor_session_unresolved"
    decision = _decide(journal, shutdown=None)
    assert (decision.resume, decision.reason) == (
        True,
        "unresolved_session_of_previous_boot",
    )


def test_an_unresolved_session_relatched_after_boot_is_anchored_to_its_launch(
    tmp_path: Path,
) -> None:
    """A supervisor without the opt-in re-latched it; the launch still names the dead boot."""
    assert _journal(tmp_path).reserve(SHUTDOWN - 600.0, FAST)
    relatch = _journal(tmp_path, session=NEW_SESSION, clock=BOOT + 57.0)
    assert not relatch.reserve(BOOT + 57.0, FAST)
    state = _state(tmp_path)
    assert state["held_boot_session"] == NEW_SESSION
    assert state["launch_boot_session"] == OLD_SESSION
    assert _decide(_journal(tmp_path, session=NEW_SESSION)).resume


def test_an_unresolved_session_of_this_boot_is_kept(tmp_path: Path) -> None:
    """Its backend may still be running; adoption rules apply instead."""
    assert _journal(tmp_path, session=NEW_SESSION).reserve(BOOT + 10.0, FAST)
    decision = _decide(_journal(tmp_path, session=NEW_SESSION))
    assert (decision.resume, decision.reason) == (False, "hold_latched_in_this_boot")


def test_an_unresolved_session_launched_after_this_boot_is_kept(tmp_path: Path) -> None:
    assert _journal(tmp_path).reserve(BOOT + 10.0, FAST)
    decision = _decide(_journal(tmp_path, session=NEW_SESSION))
    assert decision.reason == "session_launch_not_before_this_boot"


MID_SESSION = "99999999-8888-4777-8666-555555555555"


def test_an_unresolved_session_held_in_its_own_boot_is_never_released(
    tmp_path: Path,
) -> None:
    """SIGKILL (no host restart): launchd relaunched it in the same boot, which
    alerted HELD AT START and was left held. No later reboot releases it, not
    even after a post-reboot start re-reads it.
    """
    assert _journal(tmp_path).reserve(SHUTDOWN - 86_400.0, FAST)
    relaunched = _journal(tmp_path, clock=SHUTDOWN - 86_300.0)
    assert not relaunched.reserve(SHUTDOWN - 86_300.0, FAST)
    assert _state(tmp_path)["held_boot_session"] == OLD_SESSION
    decision = _decide(_journal(tmp_path, session=NEW_SESSION))
    assert (decision.resume, decision.reason) == (
        False,
        "unresolved_session_held_in_an_earlier_boot",
    )
    # The first start after the reboot neither re-stamps nor rewrites the hold,
    # so a second start in this boot still holds.
    before = (tmp_path / "events_restart_state.json").read_bytes()
    assert not _journal(tmp_path, session=NEW_SESSION, clock=BOOT + 57.0).reserve(
        BOOT + 57.0, FAST
    )
    assert (tmp_path / "events_restart_state.json").read_bytes() == before
    decision = _decide(_journal(tmp_path, session=NEW_SESSION))
    assert decision.reason == "unresolved_session_held_in_an_earlier_boot"


def test_an_unresolved_session_left_held_in_an_intermediate_boot_is_kept(
    tmp_path: Path,
) -> None:
    """Power loss, then a boot whose operator saw the hold and left it."""
    assert _journal(tmp_path).reserve(SHUTDOWN - 86_400.0, FAST)
    seen = _journal(tmp_path, session=MID_SESSION, clock=SHUTDOWN - 3_600.0)
    assert not seen.reserve(SHUTDOWN - 3_600.0, FAST)
    decision = _decide(_journal(tmp_path, session=NEW_SESSION))
    assert decision.reason == "unresolved_session_held_in_an_earlier_boot"


def test_an_unresolved_hold_persisted_without_a_boot_stamp_is_kept(
    tmp_path: Path,
) -> None:
    """Its persisting supervisor could not read its boot, so it may have been this one's."""
    assert _journal(tmp_path).reserve(SHUTDOWN - 86_400.0, FAST)
    assert not _journal(tmp_path, session=None).reserve(SHUTDOWN - 86_300.0, FAST)
    decision = _decide(_journal(tmp_path, session=NEW_SESSION))
    assert decision.reason == "hold_not_stamped_with_boot_session"


def test_an_unresolved_session_without_a_charged_launch_names_the_gap(
    tmp_path: Path,
) -> None:
    """An uncharged relaunch after the charged ones aged out of the window."""
    assert _journal(tmp_path).reserve(SHUTDOWN - 600.0, FAST, charged=False)
    journal = _journal(tmp_path, session=NEW_SESSION)
    assert journal.launch_times == []
    decision = _decide(journal)
    assert (decision.resume, decision.reason) == (False, "session_launch_time_unknown")


# --------------------------------------------------------------------------- #
# supervision end to end (a stub backend, injected boot identity)
# --------------------------------------------------------------------------- #


def _supervise(
    tmp_path: Path,
    plan: str,
    *,
    boot: BootIdentity,
    resume: bool = False,
    stop: sup._StopFlag | None = None,
    shutdown: float | None = None,
    reads: list[str] | None = None,
) -> tuple[int, sup.SupervisorPaths, _Recorder]:
    paths = _paths(tmp_path)
    recorder = _Recorder()

    def identity() -> BootIdentity:
        if reads is not None:
            reads.append("boot")
        return boot

    code = sup.supervise(
        _stub_command(tmp_path, plan),
        paths,
        sup.HealthThresholds(minimum_free_disk_gib=0.001),
        FAST,
        sup.Alerter([recorder]),
        interval=0.02,
        working_directory=tmp_path,
        runtime=sup.SupervisorRuntime(
            is_backend=lambda _pid: False,
            deadman=lambda _url: None,
            boot_identity=identity,
            previous_shutdown=lambda _boot_time: shutdown,
        ),
        stop=stop,
        resume_after_host_restart=resume,
    )
    return code, paths, recorder


def _stop_after_launch(tmp_path: Path) -> sup._StopFlag:
    """Deliver the shutdown's SIGTERM, as the stop flag, once the stub runs."""
    stop = sup._StopFlag()
    lock = tmp_path / "process.lock"

    def trip() -> None:
        deadline = time.time() + 10.0
        while time.time() < deadline and not lock.exists():
            time.sleep(0.01)
        time.sleep(0.1)
        stop.requested = True

    threading.Thread(target=trip, daemon=True).start()
    return stop


def _stop_once_holding(tmp_path: Path) -> sup._StopFlag:
    stop = sup._StopFlag()
    events = tmp_path / "events.jsonl"

    def trip() -> None:
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if events.exists() and '"holding"' in events.read_text():
                break
            time.sleep(0.01)
        stop.requested = True

    threading.Thread(target=trip, daemon=True).start()
    return stop


def _launches(paths: sup.SupervisorPaths) -> int:
    return [e["event"] for e in _events(paths)].count("backend_launched")


def _latch_signal_hold_in_old_boot(tmp_path: Path) -> float:
    _supervise(
        tmp_path,
        "run,exit0",
        boot=BootIdentity(OLD_SESSION, 1_000.0),
        stop=_stop_after_launch(tmp_path),
    )
    state = _state(tmp_path)
    assert state["hold_reason"] == "operator_signal_stop"
    assert state["held_boot_session"] == OLD_SESSION
    return float(state["held_at_epoch"])  # type: ignore[arg-type]


def test_opted_in_supervisor_relaunches_after_the_host_restart(tmp_path: Path) -> None:
    held_at = _latch_signal_hold_in_old_boot(tmp_path)
    boot = BootIdentity(NEW_SESSION, held_at + 60.0)
    code, paths, recorder = _supervise(
        tmp_path, "run,exit0", boot=boot, resume=True, shutdown=held_at - 0.2
    )
    events = _events(paths)
    cleared = [e for e in events if e["event"] == "hold_cleared_after_host_restart"]
    assert code == 0
    assert _launches(paths) == 2
    assert len(cleared) == 1
    assert cleared[0]["previous_reason"] == "operator_signal_stop"
    assert cleared[0]["decision"] == "latched_by_previous_boot_shutdown"
    assert cleared[0]["held_boot_session"] == OLD_SESSION
    assert cleared[0]["boot_session"] == NEW_SESSION
    relaunch = [
        t for t, _ in recorder.sent if t == RELAUNCHING_AFTER_HOST_RESTART_TITLE
    ]
    assert relaunch == [RELAUNCHING_AFTER_HOST_RESTART_TITLE]
    # The relaunch was charged to the budget like any other launch.
    assert len(_state(tmp_path)["launch_times"]) == 2  # type: ignore[arg-type]


def test_without_the_opt_in_the_start_hold_alerts_and_stays_alive(
    tmp_path: Path,
) -> None:
    """The default is unchanged semantics, minus the silent exit."""
    held_at = _latch_signal_hold_in_old_boot(tmp_path)
    before = (tmp_path / "events_restart_state.json").read_bytes()
    code, paths, recorder = _supervise(
        tmp_path,
        "run,exit0",
        boot=BootIdentity(NEW_SESSION, held_at + 60.0),
        stop=_stop_once_holding(tmp_path),
        shutdown=held_at - 0.2,
    )
    names = [e["event"] for e in _events(paths)]
    assert code == 0
    assert _launches(paths) == 1
    assert "hold_cleared_after_host_restart" not in names
    assert "host_restart_resume_declined" not in names  # never evaluated
    title, body = recorder.sent[0]
    assert title == "HYPERVECTOR SUPERVISOR HELD AT START"
    assert body.startswith("operator_signal_stop; ")
    assert "hypervector live supervisor resume" in body
    assert "--yes --enabled --i-accept-live-risk" in body
    # The SIGTERM that ended the hold latched nothing new.
    assert (tmp_path / "events_restart_state.json").read_bytes() == before


def test_an_opted_in_supervisor_in_the_same_boot_declines_and_says_why(
    tmp_path: Path,
) -> None:
    _latch_signal_hold_in_old_boot(tmp_path)
    captured: list[dict[str, object]] = []

    class _Records(_Recorder):
        def send(self, title: str, body: str, record: dict[str, object]) -> None:
            super().send(title, body, record)
            captured.append(record)

    paths = _paths(tmp_path)
    recorder = _Records()
    code = sup.supervise(
        _stub_command(tmp_path, "run,exit0"),
        paths,
        sup.HealthThresholds(minimum_free_disk_gib=0.001),
        FAST,
        sup.Alerter([recorder]),
        interval=0.02,
        working_directory=tmp_path,
        runtime=sup.SupervisorRuntime(
            is_backend=lambda _pid: False,
            deadman=lambda _url: None,
            boot_identity=lambda: BootIdentity(OLD_SESSION, 1_000.0),
            previous_shutdown=_no_shutdown_reader,
        ),
        stop=_stop_once_holding(tmp_path),
        resume_after_host_restart=True,
    )
    declined = [
        e for e in _events(paths) if e["event"] == "host_restart_resume_declined"
    ]
    assert code == 0
    assert _launches(paths) == 1
    assert [e["decision"] for e in declined] == ["hold_latched_in_this_boot"]
    assert recorder.sent[0][0] == "HYPERVECTOR SUPERVISOR HELD AT START"
    assert captured[0]["resume_declined"] == "hold_latched_in_this_boot"
    assert captured[0]["held_boot_session"] == OLD_SESSION


def test_a_stop_file_keeps_the_hold_across_a_host_restart(tmp_path: Path) -> None:
    held_at = _latch_signal_hold_in_old_boot(tmp_path)
    (tmp_path / "STOP").write_text("operator stop")
    code, paths, _ = _supervise(
        tmp_path,
        "run,exit0",
        boot=BootIdentity(NEW_SESSION, held_at + 60.0),
        resume=True,
        shutdown=held_at - 0.2,
    )
    declined = [
        e for e in _events(paths) if e["event"] == "host_restart_resume_declined"
    ]
    assert code == 0
    assert _launches(paths) == 1
    assert [e["decision"] for e in declined] == ["operator_stop_file_present"]


def test_a_clean_exit_stop_is_never_released_by_a_restart(tmp_path: Path) -> None:
    """A STOP-file drain or bounded run (exit 0) is the durable operator stop."""
    _supervise(tmp_path, "exit0", boot=BootIdentity(OLD_SESSION, 1_000.0))
    _code, paths, recorder = _supervise(
        tmp_path,
        "exit0",
        boot=BootIdentity(NEW_SESSION, time.time() + 1.0),
        resume=True,
        stop=_stop_once_holding(tmp_path),
        shutdown=time.time(),
    )
    assert _launches(paths) == 1
    assert recorder.sent[0] == (
        "HYPERVECTOR SUPERVISOR HELD AT START",
        "clean_exit_operator_stop_or_bounded_run; archive the restart journal to resume",
    )


def test_an_opted_in_supervisor_resumes_after_power_loss(tmp_path: Path) -> None:
    command = _stub_command(tmp_path, "exit0")
    RestartJournal(
        tmp_path / "events.jsonl", command, boot_session=OLD_SESSION
    ).reserve(time.time() - 3_600.0, FAST)
    _code, paths, _ = _supervise(
        tmp_path,
        "exit0",
        boot=BootIdentity(NEW_SESSION, time.time() - 60.0),
        resume=True,
    )
    cleared = [
        e for e in _events(paths) if e["event"] == "hold_cleared_after_host_restart"
    ]
    assert [e["decision"] for e in cleared] == ["unresolved_session_of_previous_boot"]
    assert _launches(paths) == 1


def test_the_boot_identity_is_read_once_per_supervisor(tmp_path: Path) -> None:
    reads: list[str] = []
    _supervise(
        tmp_path, "exit4,exit0", boot=BootIdentity(OLD_SESSION, 1_000.0), reads=reads
    )
    assert reads == ["boot"]
    assert _state(tmp_path)["launch_boot_session"] == OLD_SESSION


def test_the_start_hold_reminds_periodically_and_exits_on_sigterm(
    tmp_path: Path,
) -> None:
    """Re-alert every reminder interval; a SIGTERM exits 0 with nothing new latched."""
    paths = _paths(tmp_path)
    journal = RestartJournal(paths.events, ["backend"], boot_session=OLD_SESSION)
    journal.hold("operator_stop_grace_expired")
    before = journal.path.read_bytes()
    clock = {"now": 2_000_000_000.0}
    stop = sup._StopFlag()
    recorder = _Recorder()

    def sleep(seconds: float) -> None:
        clock["now"] += seconds
        if clock["now"] >= 2_000_000_000.0 + 3_700.0:
            stop.requested = True

    code = sup.supervise(
        ["backend"],
        paths,
        sup.HealthThresholds(minimum_free_disk_gib=0.001),
        FAST,
        sup.Alerter([recorder], reminder_seconds=1_800.0),
        interval=30.0,
        working_directory=tmp_path,
        runtime=sup.SupervisorRuntime(
            now=lambda: clock["now"],
            sleep=sleep,
            is_backend=lambda _pid: False,
            deadman=lambda _url: None,
            boot_identity=lambda: BootIdentity(NEW_SESSION, 1_000.0),
            previous_shutdown=_no_shutdown_reader,
        ),
        stop=stop,
    )
    held = [t for t, _ in recorder.sent if t == "HYPERVECTOR SUPERVISOR HELD AT START"]
    assert code == 0
    assert len(held) == 3  # at start, +30 min, +60 min
    # Between reminders the backend-absent alert does not repeat on its own.
    assert len(recorder.sent) == 4
    assert journal.path.read_bytes() == before


def test_a_held_supervisor_exits_within_a_second_of_the_stop(tmp_path: Path) -> None:
    """A signal does not cut a sleep short (PEP 475); the hold waits in 1 s slices.

    Otherwise a bootout or ``kickstart -k`` of a held supervisor waits out a
    full 30 s poll interval, as long as the resume helper's kickstart timeout.
    """
    paths = _paths(tmp_path)
    RestartJournal(paths.events, ["backend"], boot_session=OLD_SESSION).hold(
        "operator_signal_stop"
    )
    clock = {"now": 2_000_000_000.0}
    slept: list[float] = []
    stop = sup._StopFlag()

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        clock["now"] += seconds
        stop.requested = True  # SIGTERM arrives during the first wait

    code = sup.supervise(
        ["backend"],
        paths,
        sup.HealthThresholds(minimum_free_disk_gib=0.001),
        FAST,
        sup.Alerter([_Recorder()]),
        interval=30.0,
        working_directory=tmp_path,
        runtime=sup.SupervisorRuntime(
            now=lambda: clock["now"],
            sleep=sleep,
            is_backend=lambda _pid: False,
            deadman=lambda _url: None,
            boot_identity=lambda: BootIdentity(NEW_SESSION, 1_000.0),
            previous_shutdown=_no_shutdown_reader,
        ),
        stop=stop,
    )
    assert code == 0
    assert slept == [1.0]


def test_the_held_at_start_notice_pages() -> None:
    """Emitted directly, so it is backend-critical and reaches a push channel."""
    push = _Recorder()
    alerter = sup.Alerter([alerts.BackendCriticalOnly(push)])
    alerter.emit(
        "HYPERVECTOR SUPERVISOR HELD AT START", "operator_signal_stop", {}, 1.0
    )
    assert push.sent == [
        ("HYPERVECTOR SUPERVISOR HELD AT START", "operator_signal_stop")
    ]


def _stopped() -> sup._StopFlag:
    stop = sup._StopFlag()
    stop.requested = True
    return stop


@pytest.mark.parametrize(
    "reason", ["restart_budget_exhausted", "clean_exit_operator_stop_or_bounded_run"]
)
def test_a_stop_before_the_first_launch_leaves_an_existing_hold_untouched(
    tmp_path: Path, reason: str
) -> None:
    """A SIGTERM during start-up must not turn a hold into a releasable signal stop."""
    RestartJournal(
        tmp_path / "events.jsonl",
        _stub_command(tmp_path, "exit0"),
        boot_session=OLD_SESSION,
        clock=lambda: SHUTDOWN - 86_400.0,
    ).hold(reason)
    before = (tmp_path / "events_restart_state.json").read_bytes()
    code, paths, recorder = _supervise(
        tmp_path,
        "exit0",
        boot=BootIdentity(MID_SESSION, SHUTDOWN - 600.0),
        resume=True,
        stop=_stopped(),
        shutdown=SHUTDOWN - 700.0,
    )
    assert code == 0
    assert _launches(paths) == 0
    assert recorder.sent == []
    assert (tmp_path / "events_restart_state.json").read_bytes() == before
    decision = _decide(RestartJournal(paths.events, _stub_command(tmp_path, "exit0")))
    assert (decision.resume, decision.reason) == (False, "hold_not_host_restart_class")


def test_a_stop_before_the_first_launch_still_latches_on_an_empty_journal(
    tmp_path: Path,
) -> None:
    code, paths, _ = _supervise(
        tmp_path, "exit0", boot=BootIdentity(OLD_SESSION, 1_000.0), stop=_stopped()
    )
    assert code == 0
    assert _launches(paths) == 0
    assert _state(tmp_path)["hold_reason"] == "operator_signal_stop"


def test_a_stop_pending_at_start_never_releases_a_resumable_hold(
    tmp_path: Path,
) -> None:
    held_at = _latch_signal_hold_in_old_boot(tmp_path)
    before = (tmp_path / "events_restart_state.json").read_bytes()
    code, paths, recorder = _supervise(
        tmp_path,
        "run,exit0",
        boot=BootIdentity(NEW_SESSION, held_at + 60.0),
        resume=True,
        stop=_stopped(),
        shutdown=held_at - 0.2,
    )
    names = [e["event"] for e in _events(paths)]
    assert code == 0
    assert _launches(paths) == 1  # the old boot's only
    assert "hold_cleared_after_host_restart" not in names
    assert "host_restart_resume_declined" not in names  # never evaluated
    assert recorder.sent == []
    assert (tmp_path / "events_restart_state.json").read_bytes() == before


def test_a_stop_during_the_shutdown_history_read_keeps_the_hold(
    tmp_path: Path,
) -> None:
    """The wtmpx child can take up to 10 s; a SIGTERM inside it wins."""
    held_at = _latch_signal_hold_in_old_boot(tmp_path)
    before = (tmp_path / "events_restart_state.json").read_bytes()
    stop = sup._StopFlag()
    paths = _paths(tmp_path)
    recorder = _Recorder()

    def shutdown_while_stopping(_boot_time: float) -> float:
        stop.requested = True
        return held_at - 0.2

    code = sup.supervise(
        _stub_command(tmp_path, "run,exit0"),
        paths,
        sup.HealthThresholds(minimum_free_disk_gib=0.001),
        FAST,
        sup.Alerter([recorder]),
        interval=0.02,
        working_directory=tmp_path,
        runtime=sup.SupervisorRuntime(
            is_backend=lambda _pid: False,
            deadman=lambda _url: None,
            boot_identity=lambda: BootIdentity(NEW_SESSION, held_at + 60.0),
            previous_shutdown=shutdown_while_stopping,
        ),
        stop=stop,
        resume_after_host_restart=True,
    )
    declined = [
        e for e in _events(paths) if e["event"] == "host_restart_resume_declined"
    ]
    assert code == 0
    assert _launches(paths) == 1
    assert [e["decision"] for e in declined] == ["stop_requested"]
    assert RELAUNCHING_AFTER_HOST_RESTART_TITLE not in [t for t, _ in recorder.sent]
    assert (tmp_path / "events_restart_state.json").read_bytes() == before


def test_a_full_volume_after_a_reboot_keeps_the_previous_boot_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Freeing the disk and restarting the supervisor then resumes as usual."""
    import cohort_supervisor_runtime as runtime_module

    held_at = _latch_signal_hold_in_old_boot(tmp_path)
    before = (tmp_path / "events_restart_state.json").read_bytes()
    free = {"gib": 0.0}
    monkeypatch.setattr(runtime_module, "free_disk_gib", lambda _path: free["gib"])
    boot = BootIdentity(NEW_SESSION, held_at + 60.0)
    captured: list[tuple[str, dict[str, object]]] = []

    class _Records(_Recorder):
        def send(self, title: str, body: str, record: dict[str, object]) -> None:
            super().send(title, body, record)
            captured.append((title, record))

    def run_once(stop: sup._StopFlag | None) -> sup.SupervisorPaths:
        paths = _paths(tmp_path)
        sup.supervise(
            _stub_command(tmp_path, "run,exit0"),
            paths,
            sup.HealthThresholds(minimum_free_disk_gib=0.001),
            FAST,
            sup.Alerter([_Records()]),
            interval=0.02,
            working_directory=tmp_path,
            runtime=sup.SupervisorRuntime(
                is_backend=lambda _pid: False,
                deadman=lambda _url: None,
                boot_identity=lambda: boot,
                previous_shutdown=lambda _boot_time: held_at - 0.2,
            ),
            stop=stop,
            resume_after_host_restart=True,
        )
        return paths

    paths = run_once(_stop_once_holding(tmp_path))
    disk = [e for e in _events(paths) if e["event"] == "refused_insufficient_free_disk"]
    assert [e["kept_hold_reason"] for e in disk] == ["operator_signal_stop"]
    assert captured[0][0] == "HYPERVECTOR DISK EXHAUSTED"
    assert captured[0][1]["hold_reason"] == "operator_signal_stop"
    assert (tmp_path / "events_restart_state.json").read_bytes() == before
    free["gib"] = 50.0
    paths = run_once(None)
    cleared = [
        e for e in _events(paths) if e["event"] == "hold_cleared_after_host_restart"
    ]
    assert [e["decision"] for e in cleared] == ["latched_by_previous_boot_shutdown"]
    assert _launches(paths) == 2


def test_an_unwritable_journal_at_start_says_the_hold_is_not_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(self: object) -> None:
        raise OSError("read-only volume")

    monkeypatch.setattr(RestartJournal, "_write", refuse)
    code, paths, recorder = _supervise(
        tmp_path,
        "exit0",
        boot=BootIdentity(OLD_SESSION, 1_000.0),
        stop=_stop_once_holding(tmp_path),
    )
    assert code == 0
    assert _launches(paths) == 0
    title, body = recorder.sent[0]
    assert title == "HYPERVECTOR SUPERVISOR HELD AT START"
    assert body.startswith("restart_journal_unwritable; hold not persisted")
    assert "archive" not in body


def test_an_adopted_backend_ending_never_triggers_the_resume(tmp_path: Path) -> None:
    """A backend that ran in this boot is not the previous boot's shutdown."""
    held_at = _latch_signal_hold_in_old_boot(tmp_path)
    before = (tmp_path / "events_restart_state.json").read_bytes()
    paths = _paths(tmp_path)
    paths.process_lock.write_text("4242", encoding="utf-8")
    alive = iter([True, True, False])
    recorder = _Recorder()
    code = sup.supervise(
        _stub_command(tmp_path, "run,exit0"),
        paths,
        sup.HealthThresholds(minimum_free_disk_gib=0.001),
        FAST,
        sup.Alerter([recorder]),
        interval=0.02,
        working_directory=tmp_path,
        adopt=True,
        adopted_exit_policy="restart",
        runtime=sup.SupervisorRuntime(
            is_backend=lambda _pid: next(alive, False),
            deadman=lambda _url: None,
            boot_identity=lambda: BootIdentity(NEW_SESSION, held_at + 60.0),
            previous_shutdown=_no_shutdown_reader,
        ),
        stop=_stop_once_holding(tmp_path),
        resume_after_host_restart=True,
    )
    names = [e["event"] for e in _events(paths)]
    assert code == 0
    assert "adopted_backend_ended" in names
    assert "hold_cleared_after_host_restart" not in names
    assert "host_restart_resume_declined" not in names
    assert _launches(paths) == 1  # the old boot's only
    assert "HYPERVECTOR SUPERVISOR HELD" in [t for t, _ in recorder.sent]
    assert "HYPERVECTOR SUPERVISOR HELD AT START" not in [t for t, _ in recorder.sent]
    assert (tmp_path / "events_restart_state.json").read_bytes() == before


# --------------------------------------------------------------------------- #
# the opt-in and the plist
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("value", "enabled"),
    [
        ("1", True),
        (" 1\n", True),
        ("0", False),
        ("", False),
        ("true", False),
        ("yes", False),
    ],
)
def test_only_the_exact_opt_in_value_enables_resume(value: str, enabled: bool) -> None:
    environment = {sup.RESUME_AFTER_HOST_RESTART_ENV: value}
    assert sup.resume_after_host_restart_enabled(environment) is enabled
    assert sup.resume_after_host_restart_enabled({}) is False


def test_the_opt_in_is_an_environment_variable_not_an_argument() -> None:
    """argv is unchanged, so enabling it needs no new command identity."""
    arguments = ["supervise", "--interval", "30", "--", "backend", "--enabled"]
    plain = plistlib.loads(
        sup.launchd_plist("supervise", arguments, python=Path("/py"))
    )
    opted = plistlib.loads(
        sup.launchd_plist(
            "supervise", arguments, python=Path("/py"), resume_after_host_restart=True
        )
    )
    assert opted["ProgramArguments"] == plain["ProgramArguments"]
    assert sup.RESUME_AFTER_HOST_RESTART_ENV not in plain["EnvironmentVariables"]
    assert opted["EnvironmentVariables"][sup.RESUME_AFTER_HOST_RESTART_ENV] == "1"
    assert opted["KeepAlive"] == {"SuccessfulExit": False}
    with pytest.raises(ValueError):
        sup.launchd_plist(
            "watch", ["watch"], python=Path("/py"), resume_after_host_restart=True
        )


def test_print_launchd_emits_the_opt_in_for_supervise_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert (
        sup.main(
            [
                "print-launchd",
                "--kind",
                "supervise",
                "--python",
                "/py",
                "--resume-after-host-restart",
                "--",
                "--interval",
                "30",
            ]
        )
        == 0
    )
    plist = plistlib.loads(capsysbinary.readouterr().out)
    assert plist["EnvironmentVariables"][sup.RESUME_AFTER_HOST_RESTART_ENV] == "1"
    assert plist["ProgramArguments"][2:] == ["supervise", "--interval", "30"]
    assert (
        sup.main(
            [
                "print-launchd",
                "--kind",
                "watch",
                "--resume-after-host-restart",
            ]
        )
        == sup.EXIT_START_REFUSED
    )


@pytest.mark.parametrize(("value", "expected"), [("1", True), (None, False)])
def test_the_supervise_command_passes_the_environment_opt_in(
    monkeypatch: pytest.MonkeyPatch, value: str | None, expected: bool
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(sup, "supervise", lambda *a, **k: captured.update(k) or 0)
    if value is None:
        monkeypatch.delenv(sup.RESUME_AFTER_HOST_RESTART_ENV, raising=False)
    else:
        monkeypatch.setenv(sup.RESUME_AFTER_HOST_RESTART_ENV, value)
    args = sup.build_parser().parse_args(
        ["supervise", "--allow-idle-sleep", "--", "backend"]
    )
    assert isinstance(args, argparse.Namespace)
    sup._run_owned(
        args, sup.SupervisorPaths(), sup.HealthThresholds(), None, None, None
    )  # type: ignore[arg-type]
    assert captured["resume_after_host_restart"] is expected


def test_production_runtime_reads_the_real_host() -> None:
    runtime = sup.SupervisorRuntime()
    assert runtime.boot_identity is host.read_boot_identity
    assert runtime.previous_shutdown is host.previous_shutdown_epoch


# --------------------------------------------------------------------------- #
# host readers (fed canned output; nothing here runs sysctl or reads wtmpx)
# --------------------------------------------------------------------------- #


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


def test_boot_identity_parses_sysctl_output() -> None:
    calls: list[list[str]] = []
    outputs = {
        "kern.bootsessionuuid": f"{NEW_SESSION.lower()}\n",
        "kern.boottime": "{ sec = 1790463001, usec = 331787 } Sat Sep 26 18:50:01 2026\n",
    }

    def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return _completed(outputs[argv[-1]])

    identity = host.read_boot_identity(run)
    assert identity == BootIdentity(NEW_SESSION, pytest.approx(BOOT))  # type: ignore[arg-type]
    assert calls == [
        ["/usr/sbin/sysctl", "-n", "kern.bootsessionuuid"],
        ["/usr/sbin/sysctl", "-n", "kern.boottime"],
    ]


def test_unreadable_boot_identity_is_unknown() -> None:
    def failing(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, 5.0)

    assert host.read_boot_identity(failing) == BootIdentity(None, None)
    assert host.read_boot_identity(lambda *a, **k: _completed("", 1)) == BootIdentity(
        None, None
    )
    assert host.parse_boot_session("not-a-uuid") is None
    assert host.parse_boot_session(f"{NEW_SESSION} {NEW_SESSION}") is None
    assert host.parse_boot_time("garbage") is None


def test_previous_shutdown_is_the_record_just_before_this_boot() -> None:
    """Newest first, as this host's wtmpx read on 2026-09-26."""
    records = [
        (7, BOOT + 30.0),  # a login after boot: ignored
        (host.BOOT_TIME_RECORD, BOOT),
        (host.SHUTDOWN_TIME_RECORD, SHUTDOWN),
        (host.BOOT_TIME_RECORD, 1_789_490_575.148101),
    ]
    assert host.select_previous_shutdown(records, BOOT) == SHUTDOWN
    # kern.boottime read an hour later had moved 0.157 s with clock adjustment.
    assert host.select_previous_shutdown(records, 1_790_463_001.489062) == SHUTDOWN


def test_a_previous_boot_without_a_shutdown_record_is_unknown() -> None:
    """2026-09-15 and 09-14 boots: no SHUTDOWN_TIME record in between."""
    records = [
        (host.BOOT_TIME_RECORD, 1_789_490_575.148101),
        (host.BOOT_TIME_RECORD, 1_789_414_464.446441),
    ]
    assert host.select_previous_shutdown(records, 1_789_490_575.148101) is None


def test_history_that_does_not_start_at_this_boot_is_unknown() -> None:
    records = [(host.BOOT_TIME_RECORD, BOOT), (host.SHUTDOWN_TIME_RECORD, SHUTDOWN)]
    assert host.select_previous_shutdown(records, BOOT - 3_600.0) is None
    assert host.select_previous_shutdown([], BOOT) is None


def test_the_shutdown_reader_runs_isolated_and_fails_closed() -> None:
    calls: list[list[str]] = []

    def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return _completed(f"{SHUTDOWN}\n")

    assert host.previous_shutdown_epoch(BOOT, run) == SHUTDOWN
    assert calls[0][:2] == [sys.executable, "-I"]
    assert Path(calls[0][2]).name == "cohort_supervisor_host.py"
    assert calls[0][3:] == ["previous-shutdown", repr(BOOT)]
    for stdout, code in (("null\n", 0), ("oops", 0), (f"{SHUTDOWN}", 1), ("true", 0)):
        assert (
            host.previous_shutdown_epoch(BOOT, lambda *a, **k: _completed(stdout, code))
            is None
        )

    def timeout(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, 10.0)

    assert host.previous_shutdown_epoch(BOOT, timeout) is None


def test_the_child_entry_point_prints_the_selection(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        host,
        "_wtmpx_records",
        lambda: iter(
            [(host.BOOT_TIME_RECORD, BOOT), (host.SHUTDOWN_TIME_RECORD, SHUTDOWN)]
        ),
    )
    assert host.main(["previous-shutdown", repr(BOOT)]) == 0
    assert json.loads(capsys.readouterr().out) == SHUTDOWN
    assert host.main(["bogus"]) == 2
