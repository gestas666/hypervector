"""Strict read-only projection of cohort transition-drain telemetry."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import re

Record = Mapping[str, object]
_REQUEST_ID = re.compile(r"[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def transition_drain_summary(
    snapshot: Record | None,
    run_id: str,
) -> dict[str, object]:
    """Return validated backend drain truth or explicit legacy unavailability."""
    if snapshot is None:
        return _unavailable()
    payload = _mapping(snapshot.get("payload"), "cohort snapshot payload")
    value = payload.get("transition_drain")
    if value is None:
        return _unavailable()
    transition = dict(_mapping(value, "transition drain"))
    if set(transition) != _expected_fields():
        raise ValueError("transition drain fields are invalid")
    status = _text(transition.get("status"), "transition drain status")
    if status not in {"inactive", "active", "completed"}:
        raise ValueError("transition drain status is invalid")
    if _text(transition.get("run_id"), "transition drain run_id") != run_id:
        raise ValueError("transition drain run identity differs")
    _validate_profile_identity(transition, snapshot)
    _validate_transition_state(transition, status)
    return transition


def _unavailable() -> dict[str, object]:
    return {
        "status": "unavailable",
        "reason": "latest cohort snapshot does not report transition drain",
    }


def _expected_fields() -> set[str]:
    return {
        "status",
        "request_id",
        "origin_run_id",
        "run_id",
        "profile_fingerprint",
        "requested_at_utc",
        "activated_at_utc",
        "resume_count",
        "last_resumed_at_utc",
        "completed_at_utc",
    }


def _validate_profile_identity(transition: Record, snapshot: Record) -> None:
    fingerprint = _text(
        transition.get("profile_fingerprint"),
        "transition drain profile_fingerprint",
    )
    if not _SHA256.fullmatch(fingerprint):
        raise ValueError("transition drain profile fingerprint is invalid")
    snapshot_fingerprint = _text(
        snapshot.get("profile_fingerprint"),
        "cohort snapshot profile_fingerprint",
    )
    if fingerprint != snapshot_fingerprint:
        raise ValueError("transition drain profile identity differs")


def _validate_transition_state(transition: Record, status: str) -> None:
    identity = transition.get("request_id")
    lifecycle = _transition_lifecycle(transition)
    if status == "inactive":
        _validate_inactive(identity, lifecycle)
        return
    if not isinstance(identity, str) or not _REQUEST_ID.fullmatch(identity):
        raise ValueError("transition drain request id is invalid")
    requested_at = _timestamp(lifecycle.requested, "requested_at_utc")
    activated_at = _timestamp(lifecycle.activated, "activated_at_utc")
    resumed_at = _optional_timestamp(lifecycle.resumed, "last_resumed_at_utc")
    completed_at = _optional_timestamp(lifecycle.completed, "completed_at_utc")
    if (status == "completed") != (completed_at is not None):
        raise ValueError("transition drain completion is inconsistent")
    if requested_at > activated_at or (
        completed_at is not None and activated_at > completed_at
    ):
        raise ValueError("transition drain chronology is invalid")
    _validate_resume(
        transition, lifecycle.count, activated_at, resumed_at, completed_at
    )


class _Lifecycle:
    def __init__(self, values: Record) -> None:
        self.origin = values.get("origin_run_id")
        self.requested = values.get("requested_at_utc")
        self.activated = values.get("activated_at_utc")
        self.count = _resume_count(values.get("resume_count"))
        self.resumed = values.get("last_resumed_at_utc")
        self.completed = values.get("completed_at_utc")


def _transition_lifecycle(transition: Record) -> _Lifecycle:
    return _Lifecycle(transition)


def _validate_inactive(identity: object, lifecycle: _Lifecycle) -> None:
    values = (
        identity,
        lifecycle.origin,
        lifecycle.requested,
        lifecycle.activated,
        lifecycle.resumed,
        lifecycle.completed,
    )
    if lifecycle.count != 0 or any(value is not None for value in values):
        raise ValueError("inactive transition drain carries lifecycle evidence")


def _validate_resume(
    transition: Record,
    count: int,
    activated: datetime,
    resumed: datetime | None,
    completed: datetime | None,
) -> None:
    origin = _text(transition.get("origin_run_id"), "transition drain origin_run_id")
    current = _text(transition.get("run_id"), "transition drain run_id")
    if count == 0:
        if resumed is not None or origin != current:
            raise ValueError("transition drain resume state is inconsistent")
        return
    if resumed is None or origin == current:
        raise ValueError("transition drain resume state is inconsistent")
    if resumed < activated or (completed is not None and resumed > completed):
        raise ValueError("transition drain resume chronology is invalid")


def _timestamp(value: object, label: str) -> datetime:
    text = _text(value, f"transition drain {label}")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"transition drain {label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"transition drain {label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _optional_timestamp(value: object, label: str) -> datetime | None:
    return None if value is None else _timestamp(value, label)


def _resume_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("transition drain resume_count is invalid")
    return value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
