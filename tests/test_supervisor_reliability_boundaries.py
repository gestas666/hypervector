"""Regression requirements for reproduced backend and supervisor failures."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from hyperliquid.utils.error import ServerError

import cohort_supervisor_alerts as alerts
import cohort_supervisor_runtime as runtime
from cohort_supervisor_state import RestartJournal
from native_runner_partial_case_fixture import partial_case
from test_cohort_backend_supervisor import FAST, _Recorder, _events, _run
from test_native_replay_adapter import deny_external_ports

from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError

__all__ = ["deny_external_ports"]


def test_event_log_failure_enters_monitored_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing fault journal must not prevent ownership monitoring."""
    hold = Mock(return_value=0)
    monkeypatch.setattr(runtime, "_hold", hold)
    monkeypatch.setattr(
        runtime, "append_jsonl", Mock(side_effect=OSError("event log unavailable"))
    )
    code, paths, recorder = _run(tmp_path, "exit0")
    assert code == 0 and hold.call_count == 1
    state = json.loads(paths.events.with_name("events_restart_state.json").read_text())
    assert state["hold_reason"] == "supervisor_faulted:OSError"
    assert any("FAULTED" in title for title, _body in recorder.sent)


def test_unpersisted_stop_cannot_rearm_a_later_supervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interrupted journal write cannot erase the durable stop obligation."""
    original = RestartJournal._write

    def refuse_hold(self: RestartJournal) -> None:
        if self.hold_reason is not None:
            raise OSError("hold persistence unavailable")
        original(self)

    hold = Mock(return_value=0)
    monkeypatch.setattr(RestartJournal, "_write", refuse_hold)
    monkeypatch.setattr(runtime, "_hold", hold)
    _code, paths, _recorder = _run(tmp_path, "exit0")
    _run(tmp_path, "exit0")
    assert len([row for row in _events(paths) if row["event"] == "backend_launched"]) == 1
    assert hold.called


def test_unfinished_supervisor_session_does_not_grant_a_fresh_launch(tmp_path: Path) -> None:
    """The launch reservation itself must prove a previous session ended safely."""
    events = tmp_path / "events.jsonl"
    first = RestartJournal(events, ["backend"])
    assert first.reserve(1000.0, FAST)
    recovered = RestartJournal(events, ["backend"])
    assert not recovered.reserve(1001.0, FAST)
    assert recovered.hold_reason == "previous_supervisor_session_unresolved"


def test_alert_journal_failure_does_not_suppress_other_channels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Durability failure is visible while independent notifications still work."""
    recorder = _Recorder()
    monkeypatch.setattr(
        alerts, "append_jsonl", Mock(side_effect=OSError("private filesystem path"))
    )
    alerts.Alerter([alerts.JsonlSink(tmp_path / "alerts.jsonl"), recorder]).emit(
        "fault", "log unavailable", {}, 1000.0
    )
    assert recorder.sent == [("fault", "log unavailable")]
    diagnostic = capsys.readouterr().err
    assert json.loads(diagnostic)["event"] == "alert_delivery_failed"
    assert "private filesystem path" not in diagnostic


def test_real_partial_close_read_failure_surfaces_as_execution_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A post-close 502 cannot emit a heartbeat claiming no order was attempted."""
    case = partial_case(tmp_path, "BTC", "stop", False, partial_close=True)
    engine = case.replay.engines["BTC"]
    original = engine._adapter.reconcile

    def fail_after_close() -> SolReconciliationSnapshot:
        if case.replay.mutations.count("close"):
            raise ServerError(502, "post-close read failure")
        return original()

    monkeypatch.setattr(engine._adapter, "reconcile", fail_after_close)
    monkeypatch.setattr(case.runner, "start", lambda **kwargs: None)
    with pytest.raises(SolLiveEngineError) as error:
        case.runner.run(max_polls=1)
    assert isinstance(error.value.__cause__, ServerError)
    assert case.replay.mutations.count("close") == 1
    assert not any(
        row["event_type"] == "heartbeat" and row["payload"].get("status") == "degraded"
        for row in case.ledger.read_all()
    )


def test_launchd_timeout_and_child_grace_fit_observed_macos_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deployed shutdown budget must fit the measured 60-second launchd cap."""
    import plistlib
    from cohort_backend_supervisor import launchd_plist
    monkeypatch.setattr(runtime.os, "killpg", Mock())
    child = Mock(pid=777)
    assert runtime._terminate_group(child)
    child.wait.assert_called_once_with(timeout=30.0)
    plist = plistlib.loads(launchd_plist("supervise", ["supervise"], python=Path("/python")))
    assert plist["ExitTimeOut"] == 60


def test_stop_is_latched_before_waiting_for_child() -> None:
    """A launchd kill during child shutdown cannot erase operator-stop evidence."""
    stop = runtime._StopFlag()
    stop.requested = True
    child = Mock(pid=777)
    child.poll.return_value = None
    order: list[str] = []
    from unittest.mock import patch
    with patch.object(runtime, "_terminate_group", side_effect=lambda _child: order.append("wait") or True):
        runtime._watch_child(child, Mock(), Mock(), FAST, Mock(), stop, Mock(),
                             interval=30, started=0, deadman_url=None,
                             on_stop=lambda: order.append("persist"))
    assert order == ["persist", "wait"]


def test_operator_signal_interrupts_long_health_sleep() -> None:
    """Routine health cadence cannot consume the whole shutdown allowance."""
    stop = runtime._StopFlag()
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        stop.requested = True

    clock = runtime.SupervisorRuntime(now=lambda: 10.0, sleep=sleep)
    runtime._interruptible_sleep(30, stop, clock)
    assert sleeps == [1.0]
