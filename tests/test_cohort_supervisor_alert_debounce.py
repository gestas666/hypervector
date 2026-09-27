"""Flapping informational probes stop bannering; critical alerts are unchanged.

2026-09-25..26: 64 informational banners in 40.8 h, mostly roster-observer flaps
of 120-150 s, each with the same alarm sound as a backend-critical alert.
Nothing here touches a notification endpoint: osascript is replaced.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

import cohort_backend_supervisor as sup
import cohort_supervisor_alerts as alerts
from cohort_supervisor_models import (
    BACKEND_CRITICAL_PROBLEMS,
    FLAPPING_INFORMATIONAL_PROBLEMS,
)
from test_cohort_backend_supervisor import _report

ROSTER = "roster_observer_unavailable"
FEE = "hip3_active_fee_evidence_unavailable"


class _Recorder:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict[str, object]]] = []

    def send(self, title: str, body: str, record: dict[str, object]) -> None:
        self.sent.append((title, body, record))

    def banners(self) -> list[tuple[str, str]]:
        return [
            (t, b) for t, b, r in self.sent if r.get(alerts.BANNER_KEY) is not False
        ]


def _alerter(recorder: _Recorder, **kwargs: float) -> alerts.Alerter:
    return alerts.Alerter(
        [recorder], reminder_seconds=1_800.0, debounce_seconds=600.0, **kwargs
    )


def test_the_debounced_labels_are_informational_only() -> None:
    assert FLAPPING_INFORMATIONAL_PROBLEMS == {ROSTER, FEE}
    assert not FLAPPING_INFORMATIONAL_PROBLEMS & BACKEND_CRITICAL_PROBLEMS


def test_a_flap_shorter_than_the_debounce_is_journaled_not_bannered(
    tmp_path: Path,
) -> None:
    """The 2026-09-26 22:15:55Z flap: both labels, cleared 150 s later."""
    recorder = _Recorder()
    journal = tmp_path / "alerts.jsonl"
    alerter = alerts.Alerter(
        [alerts.JsonlSink(journal), recorder], debounce_seconds=600.0
    )
    assert alerter.observe(_report(), 0.0) is False
    assert alerter.observe(_report(FEE, ROSTER), 30.0) is False
    assert alerter.observe(_report(FEE, ROSTER), 150.0) is False
    assert alerter.observe(_report(), 180.0) is False
    assert recorder.banners() == []
    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    assert sorted(row["debounced_problem"] for row in rows) == [FEE, ROSTER]
    assert all(row["banner"] is False for row in rows)
    assert all(row["cleared_after_seconds"] == 150.0 for row in rows)
    assert all(row["alert_class"] == "informational" for row in rows)


def test_a_label_that_persists_past_the_debounce_is_announced_once_settled() -> None:
    recorder = _Recorder()
    alerter = _alerter(recorder)
    alerter.observe(_report(), 0.0)
    for now in (30.0, 300.0, 599.0):
        assert alerter.observe(_report(ROSTER), now) is False
    assert alerter.observe(_report(ROSTER), 630.0) is True
    assert alerter.observe(_report(), 700.0) is True
    assert recorder.banners() == [
        ("Hypervector notice", ROSTER),
        ("Hypervector recovered", "all probes healthy"),
    ]
    assert all(r["alert_class"] == "informational" for _t, _b, r in recorder.sent)


def test_critical_labels_are_never_debounced() -> None:
    """The critical alert is immediate; a pending flap is left out of its body."""
    recorder = _Recorder()
    alerter = _alerter(recorder)
    alerter.observe(_report(), 0.0)
    assert alerter.observe(_report(ROSTER, "backend_process_absent"), 30.0) is True
    title, body, record = recorder.sent[0]
    assert title == "HYPERVECTOR BACKEND ALERT"
    assert body == "backend_process_absent"
    assert record["debounced_problems"] == [ROSTER]
    assert record["alert_class"] == "backend_critical"


def test_a_recovery_while_a_label_is_debouncing_names_that_label() -> None:
    """The critical condition cleared; the roster is still down, just unsettled."""
    recorder = _Recorder()
    alerter = _alerter(recorder)
    alerter.observe(_report(), 0.0)
    assert alerter.observe(_report(ROSTER, "backend_process_absent"), 30.0) is True
    assert alerter.observe(_report(ROSTER), 90.0) is True
    title, body, record = recorder.sent[-1]
    assert title == "Hypervector recovered"
    assert body == f"no settled problems; still debouncing {ROSTER}"
    assert record["debounced_problems"] == [ROSTER]
    assert record["alert_class"] == "backend_critical"  # the push channel learns too


@pytest.mark.parametrize("label", ["roster_observer_stale", "checkpoint_stale"])
def test_other_informational_labels_are_not_debounced(label: str) -> None:
    """roster_observer_stale (900 s) is what still catches a dead observer."""
    recorder = _Recorder()
    alerter = _alerter(recorder)
    alerter.observe(_report(), 0.0)
    assert alerter.observe(_report(label), 30.0) is True
    assert recorder.banners() == [("Hypervector notice", label)]


def test_without_a_debounce_the_alerter_is_unchanged() -> None:
    recorder = _Recorder()
    alerter = alerts.Alerter([recorder])
    alerter.observe(_report(), 0.0)
    assert alerter.observe(_report(ROSTER), 30.0) is True
    assert alerter.observe(_report(), 60.0) is True
    assert [t for t, _b, _r in recorder.sent] == [
        "Hypervector notice",
        "Hypervector recovered",
    ]


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf"), True])
def test_an_invalid_debounce_is_refused(value: float) -> None:
    with pytest.raises(ValueError):
        alerts.Alerter([], debounce_seconds=value)


def test_the_cli_debounces_for_ten_minutes_by_default() -> None:
    for command in ("watch", "supervise", "status"):
        args = sup.build_parser().parse_args([command])
        assert args.alert_debounce_seconds == 600.0


# --------------------------------------------------------------------------- #
# banner sound
# --------------------------------------------------------------------------- #


def _banner_scripts(
    monkeypatch: pytest.MonkeyPatch, *records: dict[str, object]
) -> list[str]:
    scripts: list[str] = []

    def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        scripts.append(argv[-1])
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(alerts.subprocess, "run", run)
    sink = alerts.MacNotificationSink()
    for record in records:
        sink.send("title", "body", record)
    return scripts


def test_only_backend_critical_banners_sound_the_alarm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    informational, critical, unclassed = _banner_scripts(
        monkeypatch,
        {"alert_class": "informational"},
        {"alert_class": "backend_critical"},
        {},
    )
    assert "sound name" not in informational
    assert critical.endswith('sound name "Basso"')
    assert unclassed.endswith('sound name "Basso"')  # unknown errs loud


def test_journal_only_records_never_reach_the_banner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        _banner_scripts(
            monkeypatch, {"alert_class": "informational", alerts.BANNER_KEY: False}
        )
        == []
    )


def test_supervisor_lifecycle_notices_keep_the_alarm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scripts: list[str] = []
    monkeypatch.setattr(
        alerts.subprocess,
        "run",
        lambda argv, **_k: scripts.append(argv[-1])
        or subprocess.CompletedProcess(argv, 0),
    )
    alerter = alerts.Alerter([alerts.MacNotificationSink()])
    alerter.emit(
        "HYPERVECTOR SUPERVISOR HELD AT START", "operator_signal_stop", {}, 1.0
    )
    assert scripts and scripts[0].endswith('sound name "Basso"')
