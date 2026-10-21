"""An expired blindness bound restarts only a backend a restart can repair.

The live ledger holds account-blind streaks of 63.8 min (09-24, 32 polls) and
197.7 min (09-02, 97 polls). The runner rode both out in place. A relaunch cannot reach
an offline venue either: it waits in the start probe, then writes a bundle and
replays every ledger after connectivity returns. So when the bound expires the
runner repeats the start probe's public metadata read on a fresh session, keeps
polling while that read also fails transiently, and exits only when the venue
answers a new session while the runner's own account reads keep failing.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from test_multi_asset_bidirectional_live_script import _load_module
from test_multi_asset_live_runner_degraded_bound import _FAILED_POLL_SECONDS, _runner

from hypervector.live import cohort_venue_start_probe as venue_probe
from hypervector.live.multi_asset_live_runner_support import (
    CohortDegradedBlindnessError,
)

_OFFLINE = "transport_connection_retry_exhausted"
_PROFILE_A = Path("tests/fixtures/cohort_chain/profile_a.toml")
# 33 failed polls stay below the one-hour default; the 34th crosses it.
_POLLS_BELOW_BOUND = 33


class _Probe:
    """Answer each fresh-session reachability check from a script."""

    def __init__(self, answers: list[str | None], then: str | None) -> None:
        self.answers = list(answers)
        self.then = then
        self.calls = 0

    def __call__(self) -> str | None:
        self.calls += 1
        return self.answers.pop(0) if self.answers else self.then


def test_the_09_24_outage_is_ridden_out_in_place(tmp_path: Path) -> None:
    """Replay: 32 blind polls of about two minutes, then the network returns."""
    probe = _Probe([], then=_OFFLINE)
    runner, _, telemetry, scenario = _runner(
        tmp_path, ("account",) * 36, venue_unreachable_reason=probe
    )

    assert runner.run(max_polls=40) == 40

    assert len(telemetry.degraded_polls) == 36
    assert scenario.now - 1_000.0 > 3_600.0
    # Consulted only on the blind polls at or past the bound.
    assert probe.calls == 36 - _POLLS_BELOW_BOUND


def test_a_long_offline_outage_never_ends_the_process(tmp_path: Path) -> None:
    """The 09-02 streak (97 polls) with the host offline throughout."""
    probe = _Probe([], then=_OFFLINE)
    runner, _, telemetry, _ = _runner(
        tmp_path, ("account",) * 97, venue_unreachable_reason=probe
    )

    assert runner.run(max_polls=100) == 100
    assert len(telemetry.degraded_polls) == 97


def test_a_reachable_venue_with_blind_account_reads_still_restarts(
    tmp_path: Path,
) -> None:
    """A process-local fault a relaunch can clear keeps the one-hour bound."""
    probe = _Probe([], then=None)
    runner, _, telemetry, _ = _runner(
        tmp_path, ("account",) * 100, venue_unreachable_reason=probe
    )

    with pytest.raises(
        CohortDegradedBlindnessError,
        match="3672s across 34 consecutive polls while a fresh public venue read",
    ):
        runner.run(max_polls=500)

    assert len(telemetry.degraded_polls) == _POLLS_BELOW_BOUND + 1
    assert probe.calls == 1


def test_every_blind_poll_past_the_bound_rechecks_reachability(
    tmp_path: Path,
) -> None:
    probe = _Probe([_OFFLINE] * 5, then=None)
    runner, _, telemetry, _ = _runner(
        tmp_path, ("account",) * 100, venue_unreachable_reason=probe
    )

    with pytest.raises(CohortDegradedBlindnessError):
        runner.run(max_polls=500)

    assert probe.calls == 6
    assert len(telemetry.degraded_polls) == _POLLS_BELOW_BOUND + 6


def test_the_probe_is_not_consulted_below_the_bound(tmp_path: Path) -> None:
    probe = _Probe([], then=None)
    modes = ("account",) * _POLLS_BELOW_BOUND + ("ok",) + ("account",) * 10
    runner, _, _, _ = _runner(tmp_path, modes, venue_unreachable_reason=probe)

    assert runner.run(max_polls=50) == 50
    assert probe.calls == 0


class _Session:
    """A fake HTTP session that records each dex read and its own closing."""

    opened: list[_Session] = []

    def __init__(self, failures: dict[str, Exception]) -> None:
        self.failures = failures
        self.reads: list[str] = []
        self.closed = False
        _Session.opened.append(self)

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.closed = True

    def post(self, _url: str, *, json: dict[str, str], timeout: float) -> object:
        dex = json["dex"]
        self.reads.append(dex)
        if dex in self.failures:
            raise self.failures[dex]
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {})


def _http_error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"{status} error", response=response)


def _install_sessions(
    monkeypatch: pytest.MonkeyPatch, failures: dict[str, Exception]
) -> None:
    _Session.opened = []
    monkeypatch.setattr(
        venue_probe.requests, "Session", lambda: _Session(dict(failures))
    )


_SYMBOLS = ("BTC", "SOL", "xyz:CCC")


def test_reachable_venue_reads_every_dex_on_a_new_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_sessions(monkeypatch, {})

    assert venue_probe.fresh_session_unreachable_reason(_SYMBOLS) is None
    assert venue_probe.fresh_session_unreachable_reason(_SYMBOLS) is None

    assert len(_Session.opened) == 2
    assert all(session.closed for session in _Session.opened)
    assert _Session.opened[0].reads == ["", "xyz"]


@pytest.mark.parametrize(
    "failure,reason",
    [
        (requests.ConnectionError("no route to host"), _OFFLINE),
        (requests.Timeout("timed out"), "transport_timeout_retry_exhausted"),
        (_http_error(503), "http_server_retry_exhausted"),
    ],
)
def test_a_transient_failure_on_any_dex_is_unreachable(
    monkeypatch: pytest.MonkeyPatch, failure: Exception, reason: str
) -> None:
    """A relaunch's start probe would wait on that dex too."""
    _install_sessions(monkeypatch, {"xyz": failure})

    assert venue_probe.fresh_session_unreachable_reason(_SYMBOLS) == reason
    assert _Session.opened[0].closed


def test_a_non_transient_answer_proves_the_venue_is_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_sessions(monkeypatch, {"": _http_error(404)})

    assert venue_probe.fresh_session_unreachable_reason(_SYMBOLS) is None
    assert _Session.opened[0].reads == ["", "xyz"]


def test_core_only_profiles_read_the_core_dex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_sessions(monkeypatch, {})

    assert venue_probe.fresh_session_unreachable_reason(("BTC", "ETH")) is None
    assert _Session.opened[0].reads == [""]


def test_the_live_runner_is_built_with_the_profile_reachability_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _load_module()
    loaded = script.load_multi_asset_live_config(_PROFILE_A, mode="observe")
    # Keep the operator inbox and STOP file out of the checkout's real data/live.
    ledger = tmp_path / "live/bidirectional_cohort/cohort.jsonl"
    config = replace(loaded, cohort_ledger=ledger, stop_file=ledger.parent / "STOP")
    monkeypatch.setattr(
        script,
        "install_process_signal_stop",
        lambda *_args: SimpleNamespace(requested=False),
    )
    engines = {symbol: Mock() for symbol in config.symbols}
    runner = script._create_runner(
        config, engines, Mock(), Mock(), Mock(), "offline-profile-a-assembly"
    )
    _install_sessions(monkeypatch, {"": requests.ConnectionError("offline")})

    assert runner._venue_unreachable_reason() == _OFFLINE
    assert _Session.opened[0].reads == [""]
    for engine in engines.values():
        assert engine.mock_calls == []


def test_failed_poll_duration_matches_the_bound_fixture() -> None:
    """Guard the arithmetic the counts above rely on."""
    assert _POLLS_BELOW_BOUND * _FAILED_POLL_SECONDS < 3_600.0
    assert (_POLLS_BELOW_BOUND + 1) * _FAILED_POLL_SECONDS >= 3_600.0
