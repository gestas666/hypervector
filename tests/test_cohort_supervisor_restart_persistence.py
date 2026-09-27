"""Restart bounds must survive supervisor replacement and preserve operator stops."""

import json
from pathlib import Path
import time

import pytest

import cohort_backend_supervisor as sup
import cohort_supervisor_runtime as runtime_module
import threading

from test_cohort_backend_supervisor import (
    FAKE_HOST,
    FAST,
    _Recorder,
    _events,
    _paths,
    _run,
    _stub_command,
)


def _stop_once_held(tmp_path: Path) -> sup._StopFlag:
    """Stop a supervisor that stays alive in its start-time hold.

    A held start no longer exits 0 silently, so a replacement supervisor keeps
    running until it is signalled, as launchd would on bootout or shutdown.
    """
    events = tmp_path / "events.jsonl"

    def holding() -> int:
        return events.read_text().count('"holding"') if events.exists() else 0

    already, stop = holding(), sup._StopFlag()

    def release() -> None:
        deadline = time.time() + 10.0
        while time.time() < deadline and holding() <= already:
            time.sleep(0.01)
        stop.requested = True

    threading.Thread(target=release, daemon=True).start()
    return stop


def test_new_supervisor_cannot_reset_exhausted_restart_budget(tmp_path: Path) -> None:
    """Simulate launchd replacing a supervisor after its nonzero give-up exit."""
    _code, paths, _ = _run(tmp_path, "exit1")
    before = len([e for e in _events(paths) if e["event"] == "backend_launched"])
    code, _paths_again, recorder = _run(
        tmp_path, "exit1", stop=_stop_once_held(tmp_path)
    )
    after = len([e for e in _events(paths) if e["event"] == "backend_launched"])
    assert before == 3
    assert after == before
    assert code == 0
    assert recorder.sent[0][0] == "HYPERVECTOR SUPERVISOR HELD AT START"
    assert recorder.sent[0][1].startswith("restart_budget_exhausted; ")


def test_new_supervisor_does_not_rearm_after_clean_exit(tmp_path: Path) -> None:
    """RunAtLoad or an accidental kickstart cannot erase an operator stop."""
    _code, paths, _ = _run(tmp_path, "exit0")
    _run(tmp_path, "exit0", stop=_stop_once_held(tmp_path))
    assert len([e for e in _events(paths) if e["event"] == "backend_launched"]) == 1


def test_corrupt_durable_state_prevents_launch(tmp_path: Path) -> None:
    """Bad persistence must fail closed rather than grant a fresh restart allowance."""
    (tmp_path / "events_restart_state.json").write_text("{broken")
    _code, paths, _ = _run(tmp_path, "exit0")
    assert not any(e["event"] == "backend_launched" for e in _events(paths))


def test_stop_file_present_prevents_even_initial_launch(tmp_path: Path) -> None:
    """A standing STOP is checked before invoking any child entrypoint."""
    (tmp_path / "STOP").write_text("operator stop")
    _code, paths, _ = _run(tmp_path, "exit0")
    assert not any(e["event"] == "backend_launched" for e in _events(paths))


def test_durable_state_records_command_identity_without_command_secrets(
    tmp_path: Path,
) -> None:
    """Persistence keeps a digest and timestamps instead of copying arbitrary argv."""
    _run(tmp_path, "exit0")
    state = tmp_path / "events_restart_state.json"
    assert state.exists()
    payload = json.loads(state.read_text())
    assert len(payload["command_sha256"]) == 64
    assert len(payload["launch_times"]) == 1
    assert payload["hold_reason"] == "clean_exit_operator_stop_or_bounded_run"


def test_unwritable_journal_latches_a_hold_instead_of_launching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A journal that cannot be written must never grant an uncounted launch.

    Charging a launch that is not persisted would let every relaunch re-read an
    empty budget and retry the armed backend without bound.
    """
    journal = sup.RestartJournal(tmp_path / "events.jsonl", ["backend"])

    def refuse(self: object) -> None:
        raise OSError("read-only volume")

    monkeypatch.setattr(sup.RestartJournal, "_write", refuse)

    assert journal.reserve(1_000.0, FAST) is False
    assert journal.hold_reason == "restart_journal_unwritable"
    assert journal.launch_times == []


def test_hold_survives_an_unwritable_journal_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fail-closed latch must not unwind into a relaunchable exit code."""
    journal = sup.RestartJournal(tmp_path / "events.jsonl", ["backend"])

    def refuse(self: object) -> None:
        raise OSError("read-only volume")

    monkeypatch.setattr(sup.RestartJournal, "_write", refuse)

    journal.hold("operator_stop_file_present")

    assert journal.hold_reason == "operator_stop_file_present"
    assert journal.hold_persisted is False


def test_a_starved_volume_holds_instead_of_launching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every armed launch writes a ~1.2 GB prestart bundle before it can refuse.

    Alerting alone let a restart loop consume the volume the live ledgers grow on,
    so the free-space precondition is checked before the launch is charged.
    """
    recorder = _Recorder()
    stop = sup._StopFlag()
    threading.Timer(1.0, lambda: setattr(stop, "requested", True)).start()
    monkeypatch.setattr(runtime_module, "free_disk_gib", lambda _path: 0.5)

    paths = _paths(tmp_path)
    code = sup.supervise(
        _stub_command(tmp_path, "exit0"),
        paths,
        sup.HealthThresholds(minimum_free_disk_gib=10.0),
        FAST,
        sup.Alerter([recorder]),
        interval=0.02,
        working_directory=tmp_path,
        stop=stop,
        runtime=sup.SupervisorRuntime(
            is_backend=lambda _pid: False, deadman=lambda _url: None, **FAKE_HOST
        ),
    )
    names = [event["event"] for event in _events(paths)]

    assert code == 0
    assert "backend_launched" not in names
    assert "refused_insufficient_free_disk" in names
    assert any("DISK" in title for title, _body in recorder.sent)
