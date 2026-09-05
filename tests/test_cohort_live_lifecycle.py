"""Lifecycle evidence must distinguish stopped workers from active health."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hypervector.research.cohort_live_lifecycle import build_live_lifecycle

_NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)
_RUN = "lifecycle-regression"


@pytest.mark.parametrize(
    ("states", "status", "expected_state", "expected_health"),
    [
        (
            ("STOPPED",),
            "running",
            "stale_running_heartbeat_after_asset_stop",
            "stopped",
        ),
        (("STOPPED",), "stopped", "stopped_consistent", "stopped"),
        (("STOPPED",), "degraded", "stopped_consistent", "stopped"),
        (("OPEN",), "running", "running_consistent", "healthy"),
        (("FLAT",), "degraded", "running_degraded", "degraded"),
        (("OPEN",), "stopped", "cohort_not_running_while_assets_active", "unknown"),
        (("FLAT", "STOPPED"), "running", "mixed_asset_lifecycle", "unknown"),
        (("FAULTED",), "running", "asset_faulted", "unknown"),
        ((None,), "running", "lifecycle_evidence_incomplete", "unknown"),
        ((), "running", "lifecycle_evidence_incomplete", "unknown"),
    ],
)
def test_control_states_determine_health(
    states: tuple[str | None, ...],
    status: str,
    expected_state: str,
    expected_health: str,
) -> None:
    """Stopped execution cannot become healthy from a stale status field."""
    result = build_live_lifecycle(
        [_event("heartbeat", {"status": status})],
        {
            str(index): [_event("state_transition", {"state": state})]
            for index, state in enumerate(states)
        },
        run_id=_RUN,
        observed_at=_NOW,
        heartbeat_stale_after_seconds=60,
    )
    assert result["state"] == expected_state
    assert result["backend_process_health"] == expected_health


def test_missing_heartbeat_is_not_fresh_from_asset_activity() -> None:
    """Venue activity alone does not establish a healthy backend heartbeat."""
    result = build_live_lifecycle(
        [],
        {"BTC": [_event("state_transition", {"state": "OPEN"})]},
        run_id=_RUN,
        observed_at=_NOW,
        heartbeat_stale_after_seconds=60,
    )
    assert result["backend_process_health"] == "stale"
    assert result["cohort_heartbeat_age_seconds"] is None


@pytest.mark.parametrize(
    ("timestamp", "message"),
    [(42, "must be text"), ("2026-09-05T12:00:00", "must be timezone-aware")],
)
def test_malformed_heartbeat_time_is_rejected(timestamp: object, message: str) -> None:
    """Malformed timestamp evidence cannot yield a health classification."""
    heartbeat = _event("heartbeat", {"status": "running"})
    heartbeat["observed_at_utc"] = timestamp
    with pytest.raises(ValueError, match=message):
        build_live_lifecycle(
            [heartbeat],
            {},
            run_id=_RUN,
            observed_at=_NOW,
            heartbeat_stale_after_seconds=60,
        )


@pytest.mark.parametrize("payload", [None, {"status": 42}, {"status": " "}])
def test_malformed_status_is_rejected(payload: object) -> None:
    """Missing or malformed heartbeat payloads remain explicit input errors."""
    with pytest.raises(ValueError):
        build_live_lifecycle(
            [_event("heartbeat", payload)],
            {},
            run_id=_RUN,
            observed_at=_NOW,
            heartbeat_stale_after_seconds=60,
        )


def test_naive_observation_clock_is_rejected() -> None:
    """A local naive clock cannot be compared against UTC venue evidence."""
    with pytest.raises(ValueError, match="generation time must be timezone-aware"):
        build_live_lifecycle(
            [],
            {},
            run_id=_RUN,
            observed_at=_NOW.replace(tzinfo=None),
            heartbeat_stale_after_seconds=60,
        )


def test_invalid_staleness_threshold_is_rejected() -> None:
    """An invalid heartbeat threshold must not disable freshness checks."""
    with pytest.raises(ValueError, match="stale threshold must be positive"):
        build_live_lifecycle(
            [],
            {},
            run_id=_RUN,
            observed_at=_NOW,
            heartbeat_stale_after_seconds=0,
        )


def _event(event_type: str, payload: object) -> dict[str, object]:
    return {
        "run_id": _RUN,
        "event_type": event_type,
        "observed_at_utc": (_NOW - timedelta(seconds=1)).isoformat(),
        "payload": payload,
    }
