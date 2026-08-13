"""Transition-drain evidence in read-only cohort checkpoints."""

from __future__ import annotations

from copy import deepcopy

import pytest

from hypervector.research.cohort_live_checkpoint import build_live_checkpoint
from test_cohort_live_checkpoint import (
    _GENERATED_AT,
    _RUN_ID,
    _SYMBOLS,
    _active_asset_rows,
)
from test_multi_asset_live_audit import _cohort_rows


def _assets() -> dict[str, list[dict[str, object]]]:
    return {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS}


def _with_latest_transition(value: object) -> list[dict[str, object]]:
    rows = deepcopy(_cohort_rows())
    snapshots = [row for row in rows if row["event_type"] == "cohort_snapshot"]
    if isinstance(value, dict):
        for row in rows:
            row["profile_fingerprint"] = value.get("profile_fingerprint")
    payload = snapshots[-1]["payload"]
    assert isinstance(payload, dict)
    payload["transition_drain"] = value
    return rows


def test_legacy_checkpoint_does_not_infer_an_inactive_drain() -> None:
    """Missing old-run telemetry remains unavailable instead of safe-looking."""
    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        _assets(),
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
    )

    assert checkpoint["transition_drain"] == {
        "status": "unavailable",
        "reason": "latest cohort snapshot does not report transition drain",
    }


def test_checkpoint_preserves_explicit_active_transition_identity() -> None:
    """A backend-authored active drain is visible without inferred fields."""
    transition = {
        "status": "active",
        "request_id": "d" * 32,
        "origin_run_id": _RUN_ID,
        "run_id": _RUN_ID,
        "profile_fingerprint": "a" * 64,
        "requested_at_utc": "2026-08-02T03:59:58+00:00",
        "activated_at_utc": "2026-08-02T03:59:59+00:00",
        "resume_count": 0,
        "last_resumed_at_utc": None,
        "completed_at_utc": None,
    }

    checkpoint = build_live_checkpoint(
        _with_latest_transition(transition),
        _assets(),
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
    )

    assert checkpoint["transition_drain"] == transition


def test_checkpoint_rejects_inconsistent_completed_transition() -> None:
    """A completed label without completion evidence is not reportable."""
    transition = {
        "status": "completed",
        "request_id": "d" * 32,
        "origin_run_id": _RUN_ID,
        "run_id": _RUN_ID,
        "profile_fingerprint": "a" * 64,
        "requested_at_utc": "2026-08-02T03:59:58+00:00",
        "activated_at_utc": "2026-08-02T03:59:59+00:00",
        "resume_count": 0,
        "last_resumed_at_utc": None,
        "completed_at_utc": None,
    }

    with pytest.raises(ValueError, match="completion is inconsistent"):
        build_live_checkpoint(
            _with_latest_transition(transition),
            _assets(),
            run_id=_RUN_ID,
            generated_at=_GENERATED_AT,
        )


def test_checkpoint_rejects_transition_identity_different_from_snapshot() -> None:
    """Nested control state cannot claim a profile other than its ledger row."""
    transition = {
        "status": "active",
        "request_id": "d" * 32,
        "origin_run_id": _RUN_ID,
        "run_id": _RUN_ID,
        "profile_fingerprint": "a" * 64,
        "requested_at_utc": "2026-08-02T03:59:58+00:00",
        "activated_at_utc": "2026-08-02T03:59:59+00:00",
        "resume_count": 0,
        "last_resumed_at_utc": None,
        "completed_at_utc": None,
    }
    rows = _with_latest_transition(transition)
    snapshots = [row for row in rows if row["event_type"] == "cohort_snapshot"]
    payload = snapshots[-1]["payload"]
    assert isinstance(payload, dict)
    nested = payload["transition_drain"]
    assert isinstance(nested, dict)
    nested["profile_fingerprint"] = "b" * 64

    with pytest.raises(ValueError, match="profile identity differs"):
        build_live_checkpoint(
            rows,
            _assets(),
            run_id=_RUN_ID,
            generated_at=_GENERATED_AT,
        )


def test_checkpoint_preserves_explicit_drain_recovery_provenance() -> None:
    """A crash recovery discloses its origin and new process-run binding."""
    transition = {
        "status": "active",
        "request_id": "d" * 32,
        "origin_run_id": "cohort-live-origin",
        "run_id": _RUN_ID,
        "profile_fingerprint": "a" * 64,
        "requested_at_utc": "2026-08-02T03:59:58+00:00",
        "activated_at_utc": "2026-08-02T03:59:59+00:00",
        "resume_count": 1,
        "last_resumed_at_utc": "2026-08-02T04:00:00+00:00",
        "completed_at_utc": None,
    }

    checkpoint = build_live_checkpoint(
        _with_latest_transition(transition),
        _assets(),
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
    )

    assert checkpoint["transition_drain"] == transition


def test_checkpoint_rejects_inconsistent_drain_recovery_shape() -> None:
    """A changed run without a counted recovery cannot look authoritative."""
    transition = {
        "status": "active",
        "request_id": "d" * 32,
        "origin_run_id": "cohort-live-origin",
        "run_id": _RUN_ID,
        "profile_fingerprint": "a" * 64,
        "requested_at_utc": "2026-08-02T03:59:58+00:00",
        "activated_at_utc": "2026-08-02T03:59:59+00:00",
        "resume_count": 0,
        "last_resumed_at_utc": None,
        "completed_at_utc": None,
    }

    with pytest.raises(ValueError, match="resume state is inconsistent"):
        build_live_checkpoint(
            _with_latest_transition(transition),
            _assets(),
            run_id=_RUN_ID,
            generated_at=_GENERATED_AT,
        )
