"""The operator's post-reboot resume helper: dry run by default, fail closed.

Every host interaction (sysctl, ps, the wtmpx reader and launchctl) is a fake;
nothing here signals a process or talks to launchd.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

import cohort_resume_after_reboot as helper
from cohort_supervisor_host import BootIdentity
from test_cohort_backend_supervisor import _paths

OLD_SESSION = "11111111-2222-4333-8444-555555555555"
NEW_SESSION = "5A70DD99-9026-4AF1-A0A1-7B03B65D0732"
SHUTDOWN = 1_790_462_947.103214
BOOT = 1_790_463_001.331787
NOW = 1_790_464_700.0  # 2026-09-26T23:18:20Z
# The supervisor journal around the 2026-09-26 restart.
EVENTS = [
    {
        "at_utc": "2026-09-26T22:49:37.296570+00:00",
        "event": "operator_stop_grace_expired",
        "pid": 22729,
    },
    {
        "at_utc": "2026-09-26T22:49:40.068353+00:00",
        "event": "backend_exited",
        "exit_code": 5,
        "pid": 22729,
    },
    {
        "action": "give_up",
        "at_utc": "2026-09-26T22:50:58.372794+00:00",
        "event": "restart_decision",
        "reason": "operator_stop_grace_expired",
    },
]
LEGACY_JOURNAL = {
    "command_sha256": "1710c3cc39eb10e5335fa3c1136010799e843a120d54b3a2c49424e82df80cfd",
    "hold_reason": "operator_stop_grace_expired",
    "launch_times": [1790318111.1002219],
    "schema_version": 1,
    "session_active": False,
}


class _Launchd:
    def __init__(self, returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.returncode = returncode

    def __call__(
        self, argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        return subprocess.CompletedProcess(
            argv, self.returncode, stdout="", stderr="denied"
        )


def _setup(
    tmp_path: Path,
    journal: dict[str, object] | None = LEGACY_JOURNAL,
    events: list[dict[str, object]] = EVENTS,
):
    paths = _paths(tmp_path)
    if journal is not None:
        (tmp_path / "events_restart_state.json").write_text(json.dumps(journal))
    paths.events.write_text("".join(json.dumps(row) + "\n" for row in events))
    paths.alerts.write_text(
        "".join(json.dumps({"title": f"alert {n}"}) + "\n" for n in range(250))
    )
    return paths


LOADED = helper.AgentState(loaded=True, disabled=False)


def _host(**overrides: object) -> tuple[helper.Host, _Launchd]:
    launchd = overrides.pop("launchd", _Launchd())
    fields: dict[str, object] = {
        "boot_identity": lambda: BootIdentity(NEW_SESSION, BOOT),
        "previous_shutdown": lambda _boot: SHUTDOWN,
        "is_backend": lambda _pid: False,
        "backend_pids": lambda: [],
        "agent_state": lambda _uid: LOADED,
        "run": launchd,
        "now": lambda: NOW,
        "uid": 501,
        **overrides,
    }
    return helper.Host(**fields), launchd  # type: ignore[arg-type]


def test_every_host_reader_is_faked_here() -> None:
    """No test in this file may reach sysctl, ps, the wtmpx reader or launchctl."""
    host, _launchd = _host()
    defaults = helper.Host()
    for name in (
        "boot_identity",
        "previous_shutdown",
        "is_backend",
        "backend_pids",
        "agent_state",
        "run",
    ):
        assert getattr(host, name) is not getattr(defaults, name), name


def _run(paths, host: helper.Host, tmp_path: Path, *, yes: bool) -> tuple[int, dict]:
    printed: list[str] = []
    code = helper.resume(
        paths, host, yes=yes, backup_root=tmp_path / "backups", out=printed.append
    )
    return code, json.loads(printed[-1])


def _failed(report: dict) -> list[str]:
    return [check["name"] for check in report["checks"] if not check["ok"]]


def test_dry_run_on_the_2026_09_26_state_is_ready_and_changes_nothing(
    tmp_path: Path,
) -> None:
    paths = _setup(tmp_path)
    host, launchd = _host()
    code, report = _run(paths, host, tmp_path, yes=False)
    assert code == helper.EXIT_READY
    assert report["verdict"] == "ready" and report["dry_run"] is True
    assert _failed(report) == []
    assert report["evidence"]["last_backend_event"]["event"] == "backend_exited"
    assert report["evidence"]["previous_shutdown_utc"].startswith("2026-09-26T22:49:07")
    # The legacy journal has no latch time: the child's exit, 33 s after the
    # shutdown record, stands in for it.
    assert report["evidence"]["hold_anchor"] == "last_backend_event"
    assert report["evidence"]["hold_after_shutdown_seconds"] == pytest.approx(32.965)
    assert (tmp_path / "events_restart_state.json").exists()
    assert not (tmp_path / "backups").exists()
    assert launchd.calls == []


def test_yes_archives_the_journal_and_kickstarts_the_supervise_agent(
    tmp_path: Path,
) -> None:
    paths = _setup(tmp_path)
    host, launchd = _host()
    code, report = _run(paths, host, tmp_path, yes=True)
    archive = tmp_path / "backups" / "reboot_hold_20260926T231820Z"
    assert code == helper.EXIT_READY
    assert report["verdict"] == "resumed"
    assert not (tmp_path / "events_restart_state.json").exists()
    moved = json.loads((archive / "events_restart_state.json").read_text())
    assert moved == LEGACY_JOURNAL
    assert (
        len((archive / "alerts_tail.jsonl").read_text().splitlines())
        == helper.TAIL_LINES
    )
    assert len((archive / "events_tail.jsonl").read_text().splitlines()) == len(EVENTS)
    assert (
        json.loads((archive / "resume_evidence.json").read_text())["verdict"] == "ready"
    )
    assert launchd.calls == [
        [
            "/bin/launchctl",
            "kickstart",
            "-k",
            "gui/501/local.hypervector.cohort.supervise",
        ]
    ]
    last = json.loads(paths.events.read_text().splitlines()[-1])
    assert last["event"] == "restart_journal_archived_after_host_restart"
    assert last["previous_reason"] == "operator_stop_grace_expired"


def _refused(tmp_path: Path, paths, host: helper.Host, launchd: _Launchd) -> list[str]:
    code, report = _run(paths, host, tmp_path, yes=True)
    assert code == helper.EXIT_REFUSED
    assert report["verdict"] == "refused"
    assert launchd.calls == []
    assert not (tmp_path / "backups").exists()
    return _failed(report)


def test_a_stop_file_refuses(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    paths.stop_file.write_text("operator stop")
    host, launchd = _host()
    assert _refused(tmp_path, paths, host, launchd) == ["stop_file_absent"]
    assert (tmp_path / "events_restart_state.json").exists()


def test_a_live_lock_owner_refuses(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    paths.process_lock.write_text("4242")
    host, launchd = _host(is_backend=lambda pid: pid == 4242)
    assert _refused(tmp_path, paths, host, launchd) == ["no_backend_lock_owner"]


@pytest.mark.parametrize("pids", [[31337], None])
def test_any_backend_process_or_an_unreadable_process_table_refuses(
    tmp_path: Path, pids: list[int] | None
) -> None:
    paths = _setup(tmp_path)
    host, launchd = _host(backend_pids=lambda: pids)
    assert _refused(tmp_path, paths, host, launchd) == ["no_backend_process"]


@pytest.mark.parametrize(
    "reason",
    [
        "clean_exit_operator_stop_or_bounded_run",
        "live_start_refused_fail_closed",
        "restart_budget_exhausted",
        "operator_stop_file_present",
    ],
)
def test_holds_a_restart_does_not_latch_are_refused(
    tmp_path: Path, reason: str
) -> None:
    paths = _setup(tmp_path, {**LEGACY_JOURNAL, "hold_reason": reason})
    host, launchd = _host()
    assert _refused(tmp_path, paths, host, launchd) == ["hold_is_host_restart_class"]


def test_a_missing_journal_refuses(tmp_path: Path) -> None:
    paths = _setup(tmp_path, journal=None)
    host, launchd = _host()
    assert _refused(tmp_path, paths, host, launchd) == ["restart_journal_readable"]


def test_a_hold_stamped_in_this_boot_refuses(tmp_path: Path) -> None:
    journal = {
        **LEGACY_JOURNAL,
        "held_boot_session": NEW_SESSION,
        "held_at_epoch": BOOT + 300.0,
        "launch_boot_session": NEW_SESSION,
    }
    paths = _setup(tmp_path, journal)
    host, launchd = _host()
    # Latched 354 s after the previous shutdown record: not the shutdown's either.
    assert _refused(tmp_path, paths, host, launchd) == [
        "hold_latched_before_this_boot",
        "hold_latched_at_previous_shutdown",
    ]


def test_a_backend_event_after_boot_refuses(tmp_path: Path) -> None:
    """A backend ran in this boot, so the hold is not the shutdown's."""
    launched = {
        "at_utc": "2026-09-26T23:00:00+00:00",
        "event": "backend_launched",
        "pid": 1,
    }
    paths = _setup(tmp_path, events=[*EVENTS, launched])
    host, launchd = _host()
    # The legacy journal has no latch time, so the newest backend event stands in.
    assert _refused(tmp_path, paths, host, launchd) == [
        "last_backend_event_predates_boot",
        "hold_latched_at_previous_shutdown",
    ]


def test_no_backend_event_refuses(tmp_path: Path) -> None:
    paths = _setup(tmp_path, events=EVENTS[2:])
    host, launchd = _host()
    assert _refused(tmp_path, paths, host, launchd) == [
        "last_backend_event_predates_boot",
        "hold_latched_at_previous_shutdown",
    ]


def test_an_unknown_boot_refuses(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    host, launchd = _host(boot_identity=lambda: BootIdentity(None, None))
    assert set(_refused(tmp_path, paths, host, launchd)) == {
        "boot_identity_known",
        "last_backend_event_predates_boot",
        "hold_latched_at_previous_shutdown",
    }


def test_a_stamped_signal_hold_from_the_previous_boot_is_ready(tmp_path: Path) -> None:
    journal = {
        **LEGACY_JOURNAL,
        "held_boot_session": OLD_SESSION,
        "held_at_epoch": SHUTDOWN + 33.0,
        "launch_boot_session": OLD_SESSION,
    }
    paths = _setup(tmp_path, journal)
    host, _launchd = _host()
    code, report = _run(paths, host, tmp_path, yes=False)
    assert code == helper.EXIT_READY
    assert report["evidence"]["hold_after_shutdown_seconds"] == pytest.approx(33.0)


@pytest.mark.parametrize(
    "journal",
    [
        # Power loss: the session never recorded its end.
        {
            **LEGACY_JOURNAL,
            "hold_reason": None,
            "session_active": True,
            "launch_boot_session": OLD_SESSION,
        },
        # Already re-latched after boot by a supervisor without the opt-in.
        {
            **LEGACY_JOURNAL,
            "hold_reason": "previous_supervisor_session_unresolved",
            "held_boot_session": NEW_SESSION,
            "held_at_epoch": BOOT + 57.0,
            "launch_boot_session": OLD_SESSION,
        },
    ],
)
def test_an_unresolved_session_of_the_previous_boot_is_ready(
    tmp_path: Path, journal: dict[str, object]
) -> None:
    paths = _setup(tmp_path, journal)
    host, _launchd = _host()
    code, report = _run(paths, host, tmp_path, yes=False)
    assert code == helper.EXIT_READY, _failed(report)


def test_a_failed_kickstart_is_reported_after_the_archive(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    host, launchd = _host(launchd=_Launchd(returncode=113))
    code, report = _run(paths, host, tmp_path, yes=True)
    assert code == helper.EXIT_ACTION_FAILED
    assert report["verdict"] == "failed"
    assert report["kickstart"]["returncode"] == 113
    assert (
        "kickstart -k gui/501/local.hypervector.cohort.supervise" in report["failure"]
    )
    assert "bootstrap gui/501 " in report["failure"] and report["failure"].endswith(
        "local.hypervector.cohort.supervise.plist"
    )
    assert not (tmp_path / "events_restart_state.json").exists()


def test_a_journal_that_changes_after_the_checks_is_not_moved(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    journal = tmp_path / "events_restart_state.json"

    def shutdown_while_a_supervisor_writes(_boot: float) -> float:
        journal.write_text(json.dumps({**LEGACY_JOURNAL, "launch_times": [1.0]}))
        return SHUTDOWN

    host, launchd = _host(previous_shutdown=shutdown_while_a_supervisor_writes)
    code, report = _run(paths, host, tmp_path, yes=True)
    assert code == helper.EXIT_ACTION_FAILED
    assert "changed after the checks" in report["failure"]
    assert journal.exists()
    assert launchd.calls == []


def test_ps_output_is_parsed_for_the_backend_entry_point() -> None:
    output = "\n".join(
        [
            "  101 /usr/bin/python -u scripts/multi_asset_bidirectional_live.py --config x",
            "  202 /bin/zsh",
            "  303 grep multi_asset_bidirectional_live",
            "  404 python /repo/scripts/multi_asset_bidirectional_live.py",
            "  505 python scripts/multi_asset_bidirectional_live.py",
        ]
    )
    assert helper.backend_pids_from_ps(output, own_pid=505) == [101, 404]


def test_the_default_is_a_dry_run() -> None:
    assert helper.build_parser().parse_args([]).yes is False
    assert helper.build_parser().parse_args(["--yes"]).yes is True


# --------------------------------------------------------------------------- #
# review follow-ups: earlier-boot unresolved holds, the shutdown window, launchd
# --------------------------------------------------------------------------- #

MID_SESSION = "99999999-8888-4777-8666-555555555555"


@pytest.mark.parametrize("held_in", [OLD_SESSION, MID_SESSION, None])
def test_an_unresolved_hold_persisted_in_an_earlier_boot_refuses(
    tmp_path: Path, held_in: str | None
) -> None:
    """A supervisor SIGKILLed and relaunched in its own boot alerted that boot.

    Only a hold first seen in this boot (inferred, or persisted by this boot's
    supervisor) is the previous boot's end.
    """
    journal = {
        **LEGACY_JOURNAL,
        "hold_reason": "previous_supervisor_session_unresolved",
        "held_boot_session": held_in,
        "held_at_epoch": SHUTDOWN - 86_400.0,
        "launch_boot_session": OLD_SESSION,
    }
    paths = _setup(tmp_path, journal)
    host, launchd = _host()
    assert _refused(tmp_path, paths, host, launchd) == ["hold_latched_before_this_boot"]


def test_a_signal_hold_latched_long_before_the_shutdown_refuses(tmp_path: Path) -> None:
    """A deliberate bootout a day before an unrelated reboot stays stopped."""
    journal = {
        **LEGACY_JOURNAL,
        "held_boot_session": OLD_SESSION,
        "held_at_epoch": SHUTDOWN - 86_400.0,
        "launch_boot_session": OLD_SESSION,
    }
    paths = _setup(tmp_path, journal)
    host, launchd = _host()
    assert _refused(tmp_path, paths, host, launchd) == [
        "hold_latched_at_previous_shutdown"
    ]
    code, report = _run(paths, host, tmp_path, yes=False)
    assert report["evidence"]["hold_after_shutdown_seconds"] == pytest.approx(-86_400.0)
    assert report["evidence"]["hold_anchor"] == "held_at_epoch"


def test_a_signal_hold_without_a_previous_shutdown_record_refuses(
    tmp_path: Path,
) -> None:
    journal = {
        **LEGACY_JOURNAL,
        "held_boot_session": OLD_SESSION,
        "held_at_epoch": SHUTDOWN + 33.0,
        "launch_boot_session": OLD_SESSION,
    }
    paths = _setup(tmp_path, journal)
    host, launchd = _host(previous_shutdown=lambda _boot: None)
    assert _refused(tmp_path, paths, host, launchd) == [
        "hold_latched_at_previous_shutdown"
    ]


@pytest.mark.parametrize(
    ("state", "failed"),
    [
        (helper.AgentState(loaded=True, disabled=True), "supervise_agent_not_disabled"),
        (helper.AgentState(loaded=True, disabled=None), "supervise_agent_not_disabled"),
        (helper.AgentState(loaded=False, disabled=False), "supervise_agent_loaded"),
        (helper.AgentState(loaded=None, disabled=False), "supervise_agent_loaded"),
    ],
)
def test_a_disabled_or_unloaded_agent_refuses_before_the_archive(
    tmp_path: Path, state: helper.AgentState, failed: str
) -> None:
    """The journal is the evidence; it is never moved for a kickstart that would fail."""
    paths = _setup(tmp_path)
    host, launchd = _host(agent_state=lambda _uid: state)
    assert _refused(tmp_path, paths, host, launchd) == [failed]
    assert (tmp_path / "events_restart_state.json").exists()


def test_an_unloaded_agent_names_the_bootstrap_command(tmp_path: Path) -> None:
    paths = _setup(tmp_path)
    host, _launchd = _host(
        agent_state=lambda _uid: helper.AgentState(loaded=False, disabled=False)
    )
    _code, report = _run(paths, host, tmp_path, yes=False)
    (check,) = [c for c in report["checks"] if c["name"] == "supervise_agent_loaded"]
    assert "/bin/launchctl bootstrap gui/501 " in check["detail"]


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('\t"local.hypervector.cohort.supervise" => disabled', True),
        ('\t"local.hypervector.cohort.supervise" => true', True),
        ('\t"local.hypervector.cohort.supervise" => enabled', False),
        ('\t"local.hypervector.cohort.supervise" => false', False),
        ('\t"local.hypervector.cohort.supervise" => maybe', None),
        ('\t"local.hypervector.cohort.watch" => disabled', False),
    ],
)
def test_print_disabled_output_is_parsed_for_the_supervise_label(
    line: str, expected: bool | None
) -> None:
    output = f'disabled services = {{\n\t"com.apple.x" => disabled\n{line}\n}}\n'
    assert helper.parse_disabled(output, helper.SUPERVISE_LABEL) is expected


def test_the_agent_state_reader_only_reads() -> None:
    calls: list[list[str]] = []
    outputs = {
        "print": (0, "state = running\n"),
        "print-disabled": (
            0,
            'disabled services = {\n\t"local.hypervector.cohort.supervise" => enabled\n}\n',
        ),
    }

    def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        code, stdout = outputs[argv[1]]
        return subprocess.CompletedProcess(argv, code, stdout=stdout, stderr="")

    assert helper.read_agent_state(501, run) == helper.AgentState(True, False)
    assert calls == [
        ["/bin/launchctl", "print", "gui/501/local.hypervector.cohort.supervise"],
        ["/bin/launchctl", "print-disabled", "gui/501"],
    ]
    outputs["print"] = (113, "")
    outputs["print-disabled"] = (1, "")
    assert helper.read_agent_state(501, run) == helper.AgentState(False, None)

    def timeout(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, 10.0)

    assert helper.read_agent_state(501, timeout) == helper.AgentState(None, None)
