"""A retry-exhausted degraded streak stays reported between its polls.

A degraded poll only lands after the backend's read retries are exhausted, so
consecutive degraded rows arrive about 123.5 s apart. The streak's freshness
window used to be the 120 s heartbeat bound: for the last few seconds before each
next degraded poll the streak read as stopped, ``backend_polls_degraded`` cleared
and then fired again, churning the alert. The freshness window is now its own
threshold, 300 s by default, and a backend that has stopped writing is still
left to the heartbeat probe.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import cohort_backend_supervisor as sup
from test_cohort_backend_supervisor import _paths, _write_healthy_files
from test_cohort_supervisor_v94_alerts import (
    _degraded,
    _health,
    _ledger,
    _now,
    _running,
    _snapshot,
)

RETRY_EXHAUSTED_SPACING = 123.5


def _polls(start: float, count: int) -> list[float]:
    return [start + RETRY_EXHAUSTED_SPACING * index for index in range(count)]


def test_the_default_freshness_window_covers_a_retry_exhausted_poll_gap() -> None:
    limits = sup.HealthThresholds()
    assert limits.degraded_freshness_seconds == 300.0
    assert limits.degraded_freshness_seconds > RETRY_EXHAUSTED_SPACING
    assert limits.heartbeat_seconds == 120.0
    for value in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="degraded_freshness_seconds"):
            sup.HealthThresholds(degraded_freshness_seconds=value)


def test_the_streak_is_reported_just_before_the_next_degraded_poll(
    tmp_path: Path,
) -> None:
    now = _now()
    first, second = _polls(now - 121.0 - RETRY_EXHAUSTED_SPACING, 2)
    report = _health(
        tmp_path,
        _snapshot(first - 30.0, 2),
        _running(first - 30.0),
        _degraded(first),
        _degraded(second),
        now=now,
    )
    assert report.backend_degraded is not None
    assert report.backend_degraded.polls == 2
    assert "backend_polls_degraded" in report.problems


def test_watch_checks_between_degraded_polls_never_clear_the_problem(
    tmp_path: Path,
) -> None:
    """Every 30 s watch check across four retry-exhausted polls keeps the alert."""
    now = _now()
    stamps = _polls(now - 600.0, 5)
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    head = [_snapshot(stamps[0] - 30.0, 2), _running(stamps[0] - 30.0)]
    checks = [stamps[1] + 1.0 + 30.0 * step for step in range(16)]
    assert max(checks) < stamps[-1] + RETRY_EXHAUSTED_SPACING
    missing = []
    for check in checks:
        landed = [_degraded(stamp) for stamp in stamps if stamp <= check]
        _ledger(paths, *head, *landed)
        report = sup.evaluate_health(
            paths, sup.HealthThresholds(), now=check, is_backend=lambda _pid: True
        )
        if "backend_polls_degraded" not in report.problems:
            missing.append(round(check - float(max(s for s in stamps if s <= check))))
    assert missing == []


def test_the_freshness_threshold_is_the_one_applied(tmp_path: Path) -> None:
    now = _now()
    first, second = _polls(now - 121.0 - RETRY_EXHAUSTED_SPACING, 2)
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    _ledger(
        paths,
        _snapshot(first - 30.0, 2),
        _running(first - 30.0),
        _degraded(first),
        _degraded(second),
    )
    tight = sup.evaluate_health(
        paths,
        sup.HealthThresholds(degraded_freshness_seconds=100.0),
        now=now,
        is_backend=lambda _pid: True,
    )
    assert tight.backend_degraded is None
    assert "backend_polls_degraded" not in tight.problems


def test_a_streak_past_the_freshness_window_is_left_to_the_heartbeat_probe(
    tmp_path: Path,
) -> None:
    now = _now()
    first, second = _polls(now - 301.0 - RETRY_EXHAUSTED_SPACING, 2)
    report = _health(
        tmp_path,
        _snapshot(first - 30.0, 2),
        _degraded(first),
        _degraded(second),
        now=now,
    )
    assert report.backend_degraded is None
    assert "backend_polls_degraded" not in report.problems
