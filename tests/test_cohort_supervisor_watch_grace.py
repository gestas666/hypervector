"""The watch agent treats a backend waiting for the venue as still warming up.

The watch agent anchors its startup grace on the runtime lock's age. The lock is
written before the venue wait, so a wait longer than the grace was reported as
``backend_heartbeat_stale`` while the backend was only waiting. A fresh wait
marker naming the lock's own process now reads as warming, as it already does
for the supervise agent; the backend refreshes the lock once the wait returns.
"""

from __future__ import annotations

import os
from pathlib import Path
import time

import cohort_backend_supervisor as sup
from cohort_supervisor_venue_wait import MARKER_FRESH_SECONDS
from test_cohort_backend_supervisor import _paths, _write_healthy_files
from test_cohort_supervisor_venue_restart import _marker

GRACE = 1_800.0


def _backend(tmp_path: Path, *, lock_age: float, now: float) -> sup.SupervisorPaths:
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    stamp = now - lock_age
    os.utime(paths.process_lock, (stamp, stamp))
    return paths


def test_a_fresh_wait_marker_for_the_locks_process_is_warming(tmp_path: Path) -> None:
    now = time.time()
    paths = _backend(tmp_path, lock_age=2 * GRACE, now=now)
    assert sup._backend_is_warming(paths, now, GRACE) is False

    _marker(paths, 4242, now - 30.0)

    assert sup._backend_is_warming(paths, now, GRACE) is True
    report = sup.evaluate_health(
        paths,
        sup.HealthThresholds(),
        now=now,
        is_backend=lambda _pid: True,
        heartbeat_required=not sup._backend_is_warming(paths, now, GRACE),
    )
    assert "backend_heartbeat_stale" not in report.problems


def test_another_process_or_a_stale_marker_is_not_warming(tmp_path: Path) -> None:
    now = time.time()
    paths = _backend(tmp_path, lock_age=2 * GRACE, now=now)

    _marker(paths, 999, now - 30.0)
    assert sup._backend_is_warming(paths, now, GRACE) is False

    _marker(paths, 4242, now - MARKER_FRESH_SECONDS - 60.0)
    assert sup._backend_is_warming(paths, now, GRACE) is False


def test_a_young_lock_is_still_warming_without_a_marker(tmp_path: Path) -> None:
    now = time.time()
    paths = _backend(tmp_path, lock_age=60.0, now=now)
    assert sup._backend_is_warming(paths, now, GRACE) is True
    paths.process_lock.unlink()
    assert sup._backend_is_warming(paths, now, GRACE) is False
