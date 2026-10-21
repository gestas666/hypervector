"""Supervisor alert logic: degraded polls, disk early warning, protection, push filter.

Every probe here reads fixture files under ``tmp_path``. Nothing touches the live
cohort, its ledgers or any notification endpoint.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import time

import pytest

import cohort_backend_supervisor as sup
import cohort_supervisor_alerts as alerts
import cohort_supervisor_health as health
from cohort_supervisor_models import BACKEND_CRITICAL_PROBLEMS
from test_cohort_backend_supervisor import _paths, _report, _write_healthy_files

RUN = "bidirectional-live-1"


def _now() -> float:
    # Fixture files are stamped after the test picks its clock; a clock a little
    # ahead keeps their observation times in the past, as in production.
    return time.time() + 2.0


def _iso(stamp: float) -> str:
    return datetime.fromtimestamp(stamp, UTC).isoformat()


def _row(event: str, stamp: float, payload: object, *, run: str = RUN) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "sequence": 0,
            "event_type": event,
            "observed_at_utc": _iso(stamp),
            "run_id": run,
            "payload": payload,
        },
        separators=(",", ":"),
    )


def _running(stamp: float, *, run: str = RUN) -> str:
    return _row("heartbeat", stamp, {"status": "running"}, run=run)


def _degraded(
    stamp: float,
    *,
    reason: str = "ReadTimeout",
    source: str = "hyperliquid_account_reconciliation",
    run: str = RUN,
) -> str:
    return _row(
        "heartbeat",
        stamp,
        {
            "status": "degraded",
            "source": source,
            "reason": reason,
            "orders_attempted": False,
        },
        run=run,
    )


def _snapshot(stamp: float, open_positions: int, *, run: str = RUN) -> str:
    # A realistic snapshot row is tens of kilobytes; the probe must not need it
    # to be small.
    payload = {"open_position_count": open_positions, "assets": ["x" * 40_000]}
    return _row("cohort_snapshot", stamp, payload, run=run)


def _ledger(paths: sup.SupervisorPaths, *lines: str, partial: str = "") -> None:
    paths.ledger.write_text("\n".join(lines) + "\n" + partial, encoding="utf-8")


def _health(
    tmp_path: Path, *lines: str, now: float | None = None, partial: str = ""
) -> sup.HealthReport:
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    _ledger(paths, *lines, partial=partial)
    return sup.evaluate_health(
        paths,
        sup.HealthThresholds(),
        now=time.time() if now is None else now,
        is_backend=lambda _pid: True,
    )


# --------------------------------------------------------------------------- #
# backend_polls_degraded
# --------------------------------------------------------------------------- #


def test_two_degraded_polls_with_open_positions_raise_the_problem(
    tmp_path: Path,
) -> None:
    now = _now()
    report = _health(
        tmp_path,
        _snapshot(now - 50.0, 2),
        _running(now - 50.0),
        _degraded(now - 35.0, reason="ReadTimeout"),
        _degraded(now - 20.0, reason="ConnectionError"),
        now=now,
    )
    assert "backend_polls_degraded" in report.problems
    assert report.backend_degraded is not None
    assert report.backend_degraded.polls == 2
    assert report.backend_degraded.open_position_count == 2
    assert report.backend_degraded.duration_seconds == pytest.approx(35.0, abs=1.0)
    detail = report.problem_details["backend_polls_degraded"]
    assert "ConnectionError" in detail
    assert "hyperliquid_account_reconciliation" in detail
    assert "0.6 min" in detail
    assert "2 polls" in detail


def test_a_single_degraded_poll_does_not_raise_the_problem(tmp_path: Path) -> None:
    now = _now()
    report = _health(
        tmp_path,
        _snapshot(now - 30.0, 2),
        _running(now - 30.0),
        _degraded(now - 15.0),
        now=now,
    )
    assert "backend_polls_degraded" not in report.problems
    assert report.backend_degraded is not None
    assert report.backend_degraded.polls == 1


def test_degraded_rows_of_one_poll_count_as_one_poll(tmp_path: Path) -> None:
    """The profit-lock controller emits one degraded row per symbol per cycle."""
    now = _now()
    report = _health(
        tmp_path,
        _running(now - 30.0),
        _degraded(now - 15.0, source="profit_lock_candles", reason="BTC missing"),
        _degraded(now - 14.999, source="profit_lock_candles", reason="ETH missing"),
        _degraded(now - 14.998, source="profit_lock_candles", reason="SOL missing"),
        _snapshot(now - 14.9, 3),
        now=now,
    )
    assert report.backend_degraded is not None
    assert report.backend_degraded.polls == 1
    assert "backend_polls_degraded" not in report.problems


def test_degraded_polls_while_flat_wait_for_the_duration_bound(tmp_path: Path) -> None:
    now = _now()
    short = _health(
        tmp_path,
        _snapshot(now - 100.0, 0),
        _running(now - 100.0),
        *(_degraded(now - age) for age in (85.0, 70.0, 55.0, 40.0, 25.0, 10.0)),
        now=now,
    )
    assert "backend_polls_degraded" not in short.problems

    long = _health(
        tmp_path,
        _snapshot(now - 400.0, 0),
        _running(now - 400.0),
        *(_degraded(now - age) for age in range(385, 0, -15)),
        now=now,
    )
    assert "backend_polls_degraded" in long.problems
    assert "6.4 min" in long.problem_details["backend_polls_degraded"]


def test_unknown_position_count_is_treated_as_possibly_open(tmp_path: Path) -> None:
    now = _now()
    report = _health(
        tmp_path,
        _running(now - 50.0),
        _degraded(now - 35.0),
        _degraded(now - 20.0),
        now=now,
    )
    assert report.backend_degraded is not None
    assert report.backend_degraded.open_position_count is None
    assert "backend_polls_degraded" in report.problems


def test_a_running_heartbeat_ends_the_streak(tmp_path: Path) -> None:
    now = _now()
    report = _health(
        tmp_path,
        _snapshot(now - 60.0, 2),
        _degraded(now - 45.0),
        _degraded(now - 30.0),
        _snapshot(now - 15.0, 2),
        _running(now - 15.0),
        now=now,
    )
    assert report.backend_degraded is None
    assert "backend_polls_degraded" not in report.problems


def test_a_previous_runs_streak_is_not_the_current_backend(tmp_path: Path) -> None:
    now = _now()
    report = _health(
        tmp_path,
        _snapshot(now - 60.0, 2, run="old"),
        _degraded(now - 45.0, run="old"),
        _degraded(now - 30.0, run="old"),
        _row("runtime_started", now - 5.0, {}, run="new"),
        now=now,
    )
    assert report.backend_degraded is None


def test_a_terminated_run_is_not_reported_as_degraded_polling(tmp_path: Path) -> None:
    now = _now()
    report = _health(
        tmp_path,
        _snapshot(now - 60.0, 2),
        _degraded(now - 45.0),
        _degraded(now - 30.0),
        _row("runtime_fault", now - 29.0, {"exception_type": "X"}),
        now=now,
    )
    assert report.backend_degraded is None


def test_a_streak_that_stopped_writing_is_left_to_the_heartbeat_probe(
    tmp_path: Path,
) -> None:
    """Old degraded rows from a dead or restarting backend are not live polls."""
    now = _now()
    report = _health(
        tmp_path,
        _snapshot(now - 900.0, 2),
        _degraded(now - 885.0),
        _degraded(now - 870.0),
        now=now,
    )
    assert report.backend_degraded is None
    assert "backend_polls_degraded" not in report.problems


def test_partial_trailing_row_is_ignored(tmp_path: Path) -> None:
    now = _now()
    report = _health(
        tmp_path,
        _snapshot(now - 50.0, 1),
        _running(now - 50.0),
        _degraded(now - 35.0),
        _degraded(now - 20.0),
        now=now,
        partial='{"schema_version":1,"event_type":"heartbeat","payl',
    )
    assert "backend_polls_degraded" in report.problems


def test_only_the_ledger_tail_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The live decisions ledger is gigabytes; a health cycle reads its tail only."""
    now = _now()
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    body = "\n".join(
        [
            _snapshot(now - 50.0, 1),
            _running(now - 50.0),
            _degraded(now - 35.0),
            _degraded(now - 20.0),
        ]
    )
    with paths.ledger.open("w", encoding="utf-8") as handle:
        handle.write(("{" + "x" * 1_000 + "}\n") * 4_000)  # ~4 MB of old history
        handle.write(body + "\n")
    requested: list[int] = []
    original = Path.open

    class _Spy:
        def __init__(self, handle: object) -> None:
            self._handle = handle

        def __enter__(self) -> _Spy:
            return self

        def __exit__(self, *exc: object) -> None:
            self._handle.close()  # type: ignore[attr-defined]

        def seek(self, *args: int) -> int:
            return self._handle.seek(*args)  # type: ignore[attr-defined]

        def read(self, size: int = -1) -> bytes:
            requested.append(size)
            return self._handle.read(size)  # type: ignore[attr-defined]

    def spy_open(self: Path, *args: object, **kwargs: object) -> object:
        handle = original(self, *args, **kwargs)  # type: ignore[arg-type]
        return _Spy(handle) if self == paths.ledger else handle

    monkeypatch.setattr(Path, "open", spy_open)
    streak = health.backend_degraded_streak(
        paths.ledger, now=now, freshness_seconds=120.0
    )
    assert streak is not None and streak.polls == 2
    assert requested and all(0 <= size <= health.LEDGER_TAIL_BYTES for size in requested)
    assert paths.ledger.stat().st_size > health.LEDGER_TAIL_BYTES


def test_a_streak_older_than_the_window_reports_a_lower_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = _now()
    rows = [_degraded(now - age) for age in range(1_200, 0, -15)]
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    _ledger(paths, _snapshot(now - 1_215.0, 1), _running(now - 1_215.0), *rows)
    monkeypatch.setattr(health, "LEDGER_TAIL_BYTES", len(rows[0]) * 30)
    report = sup.evaluate_health(
        paths, sup.HealthThresholds(), now=now, is_backend=lambda _pid: True
    )
    assert report.backend_degraded is not None
    assert report.backend_degraded.complete is False
    assert "backend_polls_degraded" in report.problems
    assert ">=" in report.problem_details["backend_polls_degraded"]


def test_healthy_running_ledger_reports_no_degraded_streak(tmp_path: Path) -> None:
    now = _now()
    report = _health(
        tmp_path, _snapshot(now - 15.0, 2), _running(now - 15.0), now=now
    )
    assert report.backend_degraded is None
    assert report.healthy


# --------------------------------------------------------------------------- #
# free disk early warning
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("free", "expected"),
    [
        (20.0, set()),
        (13.9, {"free_disk_warning"}),
        (10.0, {"free_disk_warning"}),
        (9.9, {"free_disk_low"}),
    ],
)
def test_free_disk_warning_is_distinct_from_the_launch_floor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    free: float,
    expected: set[str],
) -> None:
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    monkeypatch.setattr(health, "free_disk_gib", lambda _path: free)
    report = sup.evaluate_health(
        paths, sup.HealthThresholds(), now=time.time(), is_backend=lambda _pid: True
    )
    disk = {p for p in report.problems if p.startswith("free_disk")}
    assert disk == expected
    for label in expected:
        assert f"{free:.1f} GiB free" in report.problem_details[label]


def test_free_disk_warning_threshold_is_validated() -> None:
    assert sup.HealthThresholds().free_disk_warning_gib == 14.0
    assert sup.HealthThresholds().minimum_free_disk_gib == 10.0
    for value in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="free_disk_warning_gib"):
            sup.HealthThresholds(free_disk_warning_gib=value)


# --------------------------------------------------------------------------- #
# protection warnings (shared contract with the backend checkpoint)
# --------------------------------------------------------------------------- #


def _checkpoint_with(paths: sup.SupervisorPaths, value: object) -> None:
    checkpoint = json.loads(paths.checkpoint.read_text())
    checkpoint["protection_warnings"] = value
    paths.checkpoint.write_text(json.dumps(checkpoint))


def _protection_report(tmp_path: Path, value: object, *, absent: bool = False):
    paths = _paths(tmp_path)
    _write_healthy_files(paths)
    if not absent:
        _checkpoint_with(paths, value)
    return sup.evaluate_health(
        paths, sup.HealthThresholds(), now=time.time(), is_backend=lambda _pid: True
    )


def test_exhausted_stop_raise_in_checkpoint_is_a_problem(tmp_path: Path) -> None:
    warning = {
        "symbol": "xyz:CCC",
        "strategy_id": "test_channel_provider",
        "entry_oid": 123456,
        "reason": "protective_stop_raise_exhausted",
        "observed_at_utc": "2026-09-24T15:00:00+00:00",
    }
    report = _protection_report(tmp_path, [warning])
    assert "protection_warning" in report.problems
    assert report.protection_warnings == (warning,)
    detail = report.problem_details["protection_warning"]
    assert "xyz:CCC" in detail
    assert "test_channel_provider" in detail
    assert "protective_stop_raise_exhausted" in detail


@pytest.mark.parametrize("value", [None, []])
def test_absent_or_empty_protection_warnings_are_healthy(
    tmp_path: Path, value: object
) -> None:
    assert _protection_report(tmp_path, value).healthy
    assert _protection_report(tmp_path, None, absent=True).healthy


@pytest.mark.parametrize("value", [{}, "broken", [None], [{"symbol": 7}]])
def test_unreadable_protection_warnings_are_not_silently_healthy(
    tmp_path: Path, value: object
) -> None:
    report = _protection_report(tmp_path, value)
    assert "protection_warning" in report.problems
    assert "unreadable" in report.problem_details["protection_warning"]


# --------------------------------------------------------------------------- #
# classification, titles and the push filter
# --------------------------------------------------------------------------- #


class _Recorder:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict[str, object]]] = []

    def send(self, title: str, body: str, record: dict[str, object]) -> None:
        self.sent.append((title, body, record))


def test_backend_critical_set_is_exactly_the_paging_problems() -> None:
    assert BACKEND_CRITICAL_PROBLEMS == {
        "backend_polls_degraded",
        "backend_process_absent",
        "backend_heartbeat_stale",
        "free_disk_low",
        "free_disk_warning",
        "protection_warning",
    }
    for local in (
        "roster_observer_unavailable",
        "roster_observer_stale",
        "hip3_fee_regime_changed",
        "hip3_fill_fee_above_threshold",
        "hip3_fill_fee_unavailable",
        "hip3_active_fee_evidence_unavailable",
    ):
        assert local not in BACKEND_CRITICAL_PROBLEMS


def _pushed_and_local(
    events: list[tuple[str, float]] | list[tuple[tuple[str, ...], float]],
) -> tuple[_Recorder, _Recorder]:
    local, push = _Recorder(), _Recorder()
    alerter = alerts.Alerter(
        [local, alerts.BackendCriticalOnly(push)], reminder_seconds=1_000.0
    )
    for problems, now in events:
        alerter.observe(_report(*problems), now)
    return local, push


def test_informational_problems_stay_local_with_a_distinct_title() -> None:
    local, push = _pushed_and_local(
        [((), 0.0), (("roster_observer_stale",), 10.0), (("roster_observer_stale",), 2_000.0)]
    )
    assert [title for title, _b, _r in local.sent] == [
        "Hypervector notice",
        "Hypervector notice",
    ]
    assert all(record["alert_class"] == "informational" for _t, _b, record in local.sent)
    assert push.sent == []


def test_backend_critical_problems_are_pushed_and_titled_as_such() -> None:
    local, push = _pushed_and_local(
        [
            ((), 0.0),
            (("roster_observer_stale",), 10.0),
            (("roster_observer_stale", "backend_polls_degraded"), 20.0),
            (("roster_observer_stale",), 30.0),
            ((), 40.0),
        ]
    )
    assert [title for title, _b, _r in local.sent] == [
        "Hypervector notice",
        "HYPERVECTOR BACKEND ALERT",
        "Hypervector backend recovered",
        "Hypervector recovered",
    ]
    assert [title for title, _b, _r in push.sent] == [
        "HYPERVECTOR BACKEND ALERT",
        "Hypervector backend recovered",
    ]
    critical_body = push.sent[0][1]
    assert critical_body.startswith("backend_polls_degraded")
    assert push.sent[0][2]["alert_class"] == "backend_critical"


def test_recovery_is_pushed_only_after_a_pushed_critical_alert() -> None:
    _local, push = _pushed_and_local(
        [((), 0.0), (("backend_heartbeat_stale",), 10.0), ((), 20.0)]
    )
    assert [title for title, _b, _r in push.sent] == [
        "HYPERVECTOR BACKEND ALERT",
        "Hypervector recovered",
    ]
    _local, quiet = _pushed_and_local(
        [((), 0.0), (("hip3_fee_regime_changed",), 10.0), ((), 20.0)]
    )
    assert quiet.sent == []


def test_backend_recovered_notice_is_retried_after_the_churn_floor() -> None:
    local, push = _Recorder(), _Recorder()
    alerter = alerts.Alerter(
        [local, alerts.BackendCriticalOnly(push)],
        reminder_seconds=10_000.0,
        minimum_interval_seconds=60.0,
    )
    alerter.observe(_report("roster_observer_stale", "backend_heartbeat_stale"), 0.0)
    assert alerter.observe(_report("roster_observer_stale"), 10.0) is False
    assert alerter.observe(_report("roster_observer_stale"), 70.0) is True
    assert [title for title, _b, _r in push.sent] == [
        "HYPERVECTOR BACKEND ALERT",
        "Hypervector backend recovered",
    ]


def test_every_critical_problem_pages() -> None:
    for problem in sorted(BACKEND_CRITICAL_PROBLEMS):
        _local, push = _pushed_and_local([((), 0.0), ((problem,), 10.0)])
        assert [title for title, _b, _r in push.sent] == ["HYPERVECTOR BACKEND ALERT"]


def test_supervisor_lifecycle_emits_are_backend_critical() -> None:
    """Give-up, hold and fault notices are emitted directly and always page."""
    local, push = _Recorder(), _Recorder()
    alerter = alerts.Alerter([local, alerts.BackendCriticalOnly(push)])
    alerter.emit("HYPERVECTOR SUPERVISOR GAVE UP", "restart_budget_exhausted", {}, 1.0)
    alerter.emit("HYPERVECTOR BACKEND HELD", "operator_stop_file_present", {}, 2.0)
    assert [title for title, _b, _r in push.sent] == [
        "HYPERVECTOR SUPERVISOR GAVE UP",
        "HYPERVECTOR BACKEND HELD",
    ]
    assert len(local.sent) == 2


def test_alert_body_carries_problem_details_critical_first() -> None:
    local = _Recorder()
    alerter = alerts.Alerter([local])
    report = sup.HealthReport(
        checked_at_utc="t",
        backend_pid=1,
        backend_alive=True,
        ledger_age_seconds=1.0,
        checkpoint_age_seconds=1.0,
        roster_age_seconds=1.0,
        stop_file_present=False,
        maximum_hip3_fill_fee_bps=None,
        problems=("roster_observer_stale", "backend_polls_degraded"),
        problem_details={
            "backend_polls_degraded": "3 polls, degraded 0.8 min, 2 open positions"
        },
    )
    alerter.observe(report, 5.0)
    assert local.sent[0][1] == (
        "backend_polls_degraded (3 polls, degraded 0.8 min, 2 open positions), "
        "roster_observer_stale"
    )


def test_configured_webhook_receives_only_backend_critical_alerts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    posted: list[bytes] = []

    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    def urlopen(request: object, timeout: float) -> _Response:
        posted.append(request.data)  # type: ignore[attr-defined]
        return _Response()

    monkeypatch.setattr(alerts.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv(alerts.WEBHOOK_ENV, "https://example.invalid/topic")
    sinks = alerts.build_sinks(
        sup.SupervisorPaths(alerts=tmp_path / "alerts.jsonl"), notifications=False
    )
    alerter = alerts.Alerter(sinks)
    alerter.observe(_report("roster_observer_unavailable"), 0.0)
    assert posted == []
    alerter.observe(_report("roster_observer_unavailable", "backend_process_absent"), 10.0)
    assert len(posted) == 1
    assert b"backend_process_absent" in posted[0]
    journal = (tmp_path / "alerts.jsonl").read_text().splitlines()
    assert len(journal) == 2
