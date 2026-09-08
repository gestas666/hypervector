"""Durable research import status must survive logging and expose recovery."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from hypervector.research.cohort_background_sync import (
    BackgroundResearchSync,
    ResearchSyncError,
)

_AT = datetime(2026, 9, 7, 22, 0, tzinfo=timezone.utc)


def test_sync_status_starts_unavailable_and_survives_consumed_success(
    tmp_path: Path,
) -> None:
    """Before the first import, neither freshness nor imported count is fabricated."""
    now = [_AT]
    controller = BackgroundResearchSync(
        tmp_path / "db",
        tmp_path,
        120,
        lambda *_: {"imported_events": 7},
        minimum_free_bytes=0,
        clock=lambda: now[0],
    )
    try:
        initial = controller.telemetry.snapshot()
        assert initial["state"] == "waiting"
        assert initial["last_success_at_utc"] is None
        assert initial["last_imported_events"] is None
        controller.poll(now=0)
        controller.wait_for_completion(timeout=2)
        now[0] += timedelta(seconds=2)
        controller.poll(now=2)
        assert controller.pop_report() == {"imported_events": 7}
        now[0] += timedelta(seconds=30)
        result = controller.telemetry.snapshot()
        assert result["state"] == "ready"
        assert result["last_success_age_seconds"] == 30
        assert result["last_imported_events"] == 7
        assert result["execution_authority"] == "none"
    finally:
        controller.close()


def test_disk_deferral_survives_logging_until_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact outage previously hidden by pop_error stays visible through retry."""
    available = [0]
    release = Event()
    monkeypatch.setattr(
        "hypervector.research.cohort_background_sync.shutil.disk_usage",
        lambda _: SimpleNamespace(free=available[0]),
    )

    def sync(*_args: Path) -> dict[str, object]:
        assert release.wait(timeout=2)
        return {"imported_events": 0}

    controller = BackgroundResearchSync(
        tmp_path / "db", tmp_path, 120, sync, minimum_free_bytes=10
    )
    try:
        controller.poll(now=0)
        error = controller.pop_error()
        assert error is not None
        assert controller.telemetry.snapshot()["state"] == "deferred"
        assert controller.telemetry.snapshot()["error"] == error
        available[0] = 20
        controller.poll(now=120)
        retry = controller.telemetry.snapshot()
        assert retry["state"] == "running" and retry["error"] == error
        release.set()
        controller.wait_for_completion(timeout=2)
        controller.poll(now=121)
        recovered = controller.telemetry.snapshot()
        assert recovered["state"] == "ready" and recovered["error"] is None
        assert recovered["last_imported_events"] == 0
    finally:
        release.set()
        controller.close()


def test_worker_failure_retains_prior_success_and_count(tmp_path: Path) -> None:
    """A failed import is distinct from zero new events or a fresh successful run."""
    attempts = []

    def sync(*_args: Path) -> dict[str, object]:
        attempts.append(1)
        if len(attempts) > 1:
            raise ResearchSyncError("bounded import timed out")
        return {"imported_events": 3}

    controller = BackgroundResearchSync(
        tmp_path / "db", tmp_path, 120, sync, minimum_free_bytes=0
    )
    try:
        controller.poll(now=0)
        controller.wait_for_completion(timeout=2)
        controller.poll(now=1)
        succeeded = controller.telemetry.snapshot()["last_success_at_utc"]
        controller.pop_report()
        controller.poll(now=120)
        with pytest.raises(ResearchSyncError):
            controller.wait_for_completion(timeout=2)
        controller.poll(now=121)
        controller.pop_error()
        failed = controller.telemetry.snapshot()
        assert failed["state"] == "failed"
        assert failed["error"] == "bounded import timed out"
        assert failed["last_success_at_utc"] == succeeded
        assert failed["last_imported_events"] == 3
    finally:
        controller.close()


def test_disabled_sync_is_distinct_from_unreported() -> None:
    """An explicitly disabled sync is a fact, while older checkpoint absence is unknown."""
    from hypervector.research.cohort_research_sync_telemetry import (
        ResearchSyncTelemetry,
    )

    status = ResearchSyncTelemetry(enabled=False).snapshot()
    assert status["state"] == "disabled"
    assert status["last_success_at_utc"] is None


@pytest.mark.parametrize("count", [-1, True, 1.5, "3"])
def test_invalid_import_count_is_rejected(count: object) -> None:
    """Malformed explicit worker counts cannot become plausible import evidence."""
    from hypervector.research.cohort_research_sync_telemetry import (
        ResearchSyncTelemetry,
    )

    tracker = ResearchSyncTelemetry()
    tracker.begin_attempt()
    with pytest.raises(ValueError, match="imported_events"):
        tracker.succeeded({"imported_events": count})


def test_invalid_clock_and_empty_failure_are_explicit() -> None:
    """Clock defects cannot create a plausible import age or an empty warning."""
    from hypervector.research.cohort_research_sync_telemetry import ResearchSyncTelemetry

    now = [_AT]
    tracker = ResearchSyncTelemetry(clock=lambda: now[0])
    tracker.begin_attempt()
    tracker.succeeded({})
    with pytest.raises(ValueError, match="actionable"):
        tracker.failed(" ")
    now[0] -= timedelta(seconds=1)
    with pytest.raises(ValueError, match="precedes"):
        tracker.snapshot()
    naive = ResearchSyncTelemetry(clock=lambda: _AT.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone-aware"):
        naive.begin_attempt()
