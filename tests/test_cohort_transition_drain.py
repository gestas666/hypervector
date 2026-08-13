"""Durable transition-drain state contract tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from hypervector.live.cohort_transition_drain import (
    CohortTransitionDrain,
    CohortTransitionDrainError,
    archive_completed_transition_drain,
    ensure_transition_drain_startable,
    load_transition_drain_snapshot,
    verify_completed_transition_drain_archive,
)

_NOW = datetime(2026, 8, 5, 13, 0, tzinfo=UTC)
_RUN = "bidirectional-live-1785934800000"
_PROFILE = "a" * 64
_REQUEST = "b" * 32


def test_activation_is_durable_identity_bound_and_idempotent(tmp_path: Path) -> None:
    """An accepted request survives a crash without changing active identity."""
    path = tmp_path / "transition_drain.json"
    control = CohortTransitionDrain(
        path=path,
        run_id=_RUN,
        profile_fingerprint=_PROFILE,
        now_fn=lambda: _NOW,
    )

    first = control.activate(
        request_id=_REQUEST,
        requested_at_utc=(_NOW - timedelta(seconds=1)).isoformat(),
    )
    second = control.activate(
        request_id=_REQUEST,
        requested_at_utc=(_NOW - timedelta(seconds=1)).isoformat(),
    )

    assert first == second
    assert control.active is True
    assert first.status == "active"
    assert first.run_id == _RUN
    assert first.profile_fingerprint == _PROFILE
    payload = json.loads(path.read_text())
    assert payload["request_id"] == _REQUEST
    assert payload["status"] == "active"
    assert set(payload) == {
        "schema_version",
        "request_id",
        "origin_run_id",
        "run_id",
        "profile_fingerprint",
        "requested_at_utc",
        "activated_at_utc",
        "resume_count",
        "last_resumed_at_utc",
        "completed_at_utc",
        "status",
    }


def test_completion_remains_a_stale_start_blocker(tmp_path: Path) -> None:
    """A drained run must be inspected and archived before another live start."""
    path = tmp_path / "transition_drain.json"
    control = CohortTransitionDrain(
        path=path,
        run_id=_RUN,
        profile_fingerprint=_PROFILE,
        now_fn=lambda: _NOW,
    )
    control.activate(
        request_id=_REQUEST,
        requested_at_utc=(_NOW - timedelta(seconds=1)).isoformat(),
    )

    completed = control.complete()

    assert completed.status == "completed"
    assert completed.completed_at_utc == _NOW.isoformat()
    assert control.active is False
    with pytest.raises(CohortTransitionDrainError, match="inspect and archive"):
        ensure_transition_drain_startable(path)


def test_existing_state_must_match_the_active_run_and_profile(tmp_path: Path) -> None:
    """A different process cannot adopt another run's transition request."""
    path = tmp_path / "transition_drain.json"
    original = CohortTransitionDrain(
        path=path,
        run_id=_RUN,
        profile_fingerprint=_PROFILE,
        now_fn=lambda: _NOW,
    )
    original.activate(
        request_id=_REQUEST,
        requested_at_utc=(_NOW - timedelta(seconds=1)).isoformat(),
    )

    with pytest.raises(CohortTransitionDrainError, match="run identity"):
        CohortTransitionDrain(
            path=path,
            run_id="different-run",
            profile_fingerprint=_PROFILE,
            now_fn=lambda: _NOW,
        )


def test_clean_path_is_startable(tmp_path: Path) -> None:
    """Absence of durable drain state permits normal pre-start validation."""
    ensure_transition_drain_startable(tmp_path / "transition_drain.json")


def test_completed_state_is_archived_recoverably_only_after_confirmation(
    tmp_path: Path,
) -> None:
    """Clearing the next-start blocker preserves exact evidence instead of deleting it."""
    path = tmp_path / "live/transition_drain.json"
    control = CohortTransitionDrain(
        path=path,
        run_id=_RUN,
        profile_fingerprint=_PROFILE,
        now_fn=lambda: _NOW,
    )
    control.activate(
        request_id=_REQUEST,
        requested_at_utc=(_NOW - timedelta(seconds=1)).isoformat(),
    )
    control.complete()
    original = path.read_bytes()
    archive_root = tmp_path / "backups/transition_drains"

    target = archive_completed_transition_drain(
        path=path,
        archive_root=archive_root,
        expected_run_id=_RUN,
        now=_NOW,
        confirmed=False,
    )

    assert path.read_bytes() == original
    assert not target.exists()

    archived = archive_completed_transition_drain(
        path=path,
        archive_root=archive_root,
        expected_run_id=_RUN,
        now=_NOW,
        confirmed=True,
    )

    assert archived == target
    assert archived.read_bytes() == original
    assert not path.exists()
    ensure_transition_drain_startable(path)


def test_completed_archive_is_verified_against_prior_run_and_profile(
    tmp_path: Path,
) -> None:
    """A profile transition accepts only exact completed drain evidence."""
    path = tmp_path / "live/transition_drain.json"
    control = CohortTransitionDrain(
        path=path,
        run_id=_RUN,
        profile_fingerprint=_PROFILE,
        now_fn=lambda: _NOW,
    )
    control.activate(
        request_id=_REQUEST,
        requested_at_utc=(_NOW - timedelta(seconds=1)).isoformat(),
    )
    control.complete()
    archived = archive_completed_transition_drain(
        path=path,
        archive_root=tmp_path / "backups/transition_drains",
        expected_run_id=_RUN,
        now=_NOW,
        confirmed=True,
    )

    snapshot = verify_completed_transition_drain_archive(
        archived,
        expected_run_id=_RUN,
        expected_profile_fingerprint=_PROFILE,
    )

    assert snapshot.status == "completed"
    assert snapshot.run_id == _RUN
    assert snapshot.profile_fingerprint == _PROFILE


@pytest.mark.parametrize(
    ("run_id", "profile_fingerprint", "message"),
    [
        ("wrong-run", _PROFILE, "run identity"),
        (_RUN, "c" * 64, "profile identity"),
    ],
)
def test_completed_archive_rejects_mismatched_prior_identity(
    tmp_path: Path,
    run_id: str,
    profile_fingerprint: str,
    message: str,
) -> None:
    """Unrelated completed evidence cannot authorize a profile change."""
    path = tmp_path / "transition_drain.json"
    control = CohortTransitionDrain(
        path=path,
        run_id=_RUN,
        profile_fingerprint=_PROFILE,
        now_fn=lambda: _NOW,
    )
    control.activate(
        request_id=_REQUEST,
        requested_at_utc=(_NOW - timedelta(seconds=1)).isoformat(),
    )
    control.complete()

    with pytest.raises(CohortTransitionDrainError, match=message):
        verify_completed_transition_drain_archive(
            path,
            expected_run_id=run_id,
            expected_profile_fingerprint=profile_fingerprint,
        )


def test_completion_rejects_a_regressed_clock_without_mutating_state(
    tmp_path: Path,
) -> None:
    """Completion chronology cannot move backward across a clock fault."""
    path = tmp_path / "transition_drain.json"
    clock = [_NOW]
    control = CohortTransitionDrain(
        path=path,
        run_id=_RUN,
        profile_fingerprint=_PROFILE,
        now_fn=lambda: clock[0],
    )
    control.activate(
        request_id=_REQUEST,
        requested_at_utc=(_NOW - timedelta(seconds=1)).isoformat(),
    )
    original = path.read_bytes()
    clock[0] = _NOW - timedelta(seconds=2)

    with pytest.raises(CohortTransitionDrainError, match="precedes activation"):
        control.complete()

    assert path.read_bytes() == original
    assert control.active is True


def test_start_gate_rejects_invalid_persisted_chronology(tmp_path: Path) -> None:
    """Malformed durable evidence cannot be archived or treated as a blocker only."""
    path = tmp_path / "transition_drain.json"
    payload = {
        "schema_version": 1,
        "request_id": _REQUEST,
        "origin_run_id": _RUN,
        "run_id": _RUN,
        "profile_fingerprint": _PROFILE,
        "requested_at_utc": _NOW.isoformat(),
        "activated_at_utc": (_NOW - timedelta(seconds=1)).isoformat(),
        "resume_count": 0,
        "last_resumed_at_utc": None,
        "completed_at_utc": None,
        "status": "active",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CohortTransitionDrainError, match="chronology"):
        ensure_transition_drain_startable(path)


def test_active_drain_can_resume_under_a_new_process_run_identity(
    tmp_path: Path,
) -> None:
    """Crash recovery preserves origin evidence while rotating process run id."""
    path = tmp_path / "transition_drain.json"
    clock = [_NOW]
    original = CohortTransitionDrain(
        path=path,
        run_id=_RUN,
        profile_fingerprint=_PROFILE,
        now_fn=lambda: clock[0],
    )
    original.activate(
        request_id=_REQUEST,
        requested_at_utc=(_NOW - timedelta(seconds=1)).isoformat(),
    )
    clock[0] = _NOW + timedelta(minutes=1)
    recovered = CohortTransitionDrain(
        path=path,
        run_id=_RUN,
        profile_fingerprint=_PROFILE,
        now_fn=lambda: clock[0],
    )

    snapshot = recovered.resume_for_run("bidirectional-live-1785934860000")

    assert snapshot.status == "active"
    assert snapshot.origin_run_id == _RUN
    assert snapshot.run_id == "bidirectional-live-1785934860000"
    assert snapshot.resume_count == 1
    assert snapshot.last_resumed_at_utc == clock[0].isoformat()
    assert recovered.active is True
    assert recovered.as_payload()["origin_run_id"] == _RUN
    assert load_transition_drain_snapshot(path) == snapshot


def test_completed_drain_cannot_be_resumed(tmp_path: Path) -> None:
    """Only an interrupted active drain may recover into a new process."""
    path = tmp_path / "transition_drain.json"
    control = CohortTransitionDrain(
        path=path,
        run_id=_RUN,
        profile_fingerprint=_PROFILE,
        now_fn=lambda: _NOW,
    )
    control.activate(
        request_id=_REQUEST,
        requested_at_utc=(_NOW - timedelta(seconds=1)).isoformat(),
    )
    control.complete()

    with pytest.raises(CohortTransitionDrainError, match="active drain"):
        control.resume_for_run("bidirectional-live-1785934860000")
