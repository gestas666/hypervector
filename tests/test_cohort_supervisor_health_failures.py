"""Monitoring must retain explicit failures without crashing or reporting health."""

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import time

import pytest

import cohort_backend_supervisor as sup
from test_cohort_backend_supervisor import (
    _Recorder,
    _paths,
    _report,
    _write_healthy_files,
)


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "unavailable", "markets": None},
        {"status": "unavailable", "markets": []},
        {"status": "available", "markets": []},
        {"status": "available", "markets": [None]},
        [],
        None,
        "broken",
        "{invalid JSON",
    ],
)
def test_unavailable_or_malformed_roster_is_unhealthy(
    tmp_path: Path,
    payload: object,
) -> None:
    """A fresh file cannot conceal an unavailable or undecodable observation."""
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    text = payload if payload == "{invalid JSON" else json.dumps(payload)
    paths.roster.write_text(text)
    report = sup.evaluate_health(
        paths,
        sup.HealthThresholds(),
        now=time.time(),
        is_backend=lambda _: True,
    )
    assert not report.healthy
    assert "roster_observer_unavailable" in report.problems


def test_rewriting_old_roster_does_not_refresh_observation(tmp_path: Path) -> None:
    """Fresh modification time cannot turn old observations into current evidence."""
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    roster = json.loads(paths.roster.read_text())
    roster["observed_at_utc"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    paths.roster.write_text(json.dumps(roster))
    report = sup.evaluate_health(
        paths,
        sup.HealthThresholds(),
        now=time.time(),
        is_backend=lambda _: True,
    )
    assert "roster_observer_stale" in report.problems


@pytest.mark.parametrize("payload", [None, [], {}, {"audit": None}])
def test_malformed_checkpoint_is_not_healthy(tmp_path: Path, payload: object) -> None:
    """Missing execution evidence is distinct from a valid empty fill history."""
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    paths.checkpoint.write_text(json.dumps(payload))
    report = sup.evaluate_health(
        paths,
        sup.HealthThresholds(),
        now=time.time(),
        is_backend=lambda _: True,
    )
    assert "checkpoint_unavailable" in report.problems


def test_stopped_roster_is_unavailable_even_when_recent(tmp_path: Path) -> None:
    """An intentional stop remains visible without waiting for its age threshold."""
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    payload = json.loads(paths.roster.read_text())
    payload["lifecycle"] = "stopped"
    paths.roster.write_text(json.dumps(payload))
    report = sup.evaluate_health(
        paths,
        sup.HealthThresholds(),
        now=time.time(),
        is_backend=lambda _: True,
    )
    assert "roster_observer_unavailable" in report.problems


@pytest.mark.parametrize("missing", [True, False])
def test_active_route_cannot_lose_fee_evidence_silently(
    tmp_path: Path, missing: bool
) -> None:
    """Missing active markets and unresolved fee regimes remain visible to operators."""
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    checkpoint = json.loads(paths.checkpoint.read_text())
    checkpoint["audit"]["run"] = {"executable_provider_symbols": ["donchian|xyz:SNDK"]}
    paths.checkpoint.write_text(json.dumps(checkpoint))
    roster = json.loads(paths.roster.read_text())
    if missing:
        roster["markets"] = roster["markets"][1:]
        roster["active_symbols"] = ["xyz:GOLD"]
    else:
        roster["markets"][0]["venue"].update(
            {"growth_mode": None, "effective_fee_status": "unresolved_growth_mode"},
        )
    paths.roster.write_text(json.dumps(roster))
    report = sup.evaluate_health(
        paths,
        sup.HealthThresholds(),
        now=time.time(),
        is_backend=lambda _: True,
    )
    assert "hip3_active_fee_evidence_unavailable" in report.problems


def test_free_disk_is_reported_and_low_space_is_a_problem(tmp_path: Path) -> None:
    """A full volume stops the ledger, the checkpoint and the next prestart bundle.

    The cohort ledger grows continuously and every armed start gzips it into a
    fresh prestart bundle, so exhaustion is reached by ordinary operation rather
    than by any fault. It has to alert before a live write fails.
    """
    paths = _paths(tmp_path)
    _write_healthy_files(paths)

    generous = sup.evaluate_health(
        paths,
        sup.HealthThresholds(minimum_free_disk_gib=0.000_001),
        now=time.time(),
        is_backend=lambda _: True,
    )
    assert generous.free_disk_gib is not None and generous.free_disk_gib > 0.0
    assert "free_disk_low" not in generous.problems
    assert generous.healthy

    starved = sup.evaluate_health(
        paths,
        sup.HealthThresholds(minimum_free_disk_gib=1_000_000.0),
        now=time.time(),
        is_backend=lambda _: True,
    )
    assert "free_disk_low" in starved.problems
    assert not starved.healthy


def test_unreadable_volume_is_unavailable_rather_than_healthy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unmeasurable free space must never be reported as sufficient free space."""
    paths = _paths(tmp_path)
    _write_healthy_files(paths)

    def refuse(_path: Path) -> object:
        raise OSError("volume unavailable")

    monkeypatch.setattr(sup.shutil, "disk_usage", refuse)
    report = sup.evaluate_health(
        paths,
        sup.HealthThresholds(),
        now=time.time(),
        is_backend=lambda _: True,
    )
    assert report.free_disk_gib is None
    assert "free_disk_unavailable" in report.problems
    assert not report.healthy


def test_free_disk_threshold_must_be_positive_and_finite() -> None:
    """An unusable disk bound is refused before any monitoring loop starts."""
    for value in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="minimum_free_disk_gib"):
            sup.HealthThresholds(minimum_free_disk_gib=value)


def test_backward_clock_step_fails_closed_on_the_heartbeat_probe(
    tmp_path: Path,
) -> None:
    """A future mtime must not read as "just written".

    `observation_age` already fails closed on exactly this condition; the ledger
    mtime probe is the only liveness signal for an owned child, so clamping a
    backward clock step to age 0 would hide a dead backend indefinitely.
    """
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    now = time.time()
    future = now + 3_600.0
    import os

    os.utime(paths.ledger, (future, future))

    report = sup.evaluate_health(
        paths, sup.HealthThresholds(), now=now, is_backend=lambda _: True
    )

    assert report.ledger_age_seconds is None
    assert "ledger_mtime_in_future" in report.problems
    assert "backend_heartbeat_stale" in report.problems
    assert not report.healthy


def test_flapping_problem_set_is_rate_limited_but_new_problems_are_not() -> None:
    """Churn must not spam; genuinely new information must never be delayed."""
    recorder = _Recorder()
    alerter = sup.Alerter(
        [recorder], reminder_seconds=10_000.0, minimum_interval_seconds=60.0
    )

    assert alerter.observe(_report("roster_observer_unavailable"), 1_000.0) is True
    # The same label leaving and returning inside the floor carries no new fact.
    assert alerter.observe(_report(), 1_010.0) is False
    assert alerter.observe(_report("roster_observer_unavailable"), 1_020.0) is False
    # A label never alerted before is new information and bypasses the floor.
    assert (
        alerter.observe(
            _report("roster_observer_unavailable", "backend_process_absent"), 1_030.0
        )
        is True
    )
    bodies = [body for _title, body in recorder.sent]
    assert "backend_process_absent" in bodies[-1]
    assert "suppressed" in bodies[-1]
