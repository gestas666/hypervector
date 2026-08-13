"""Durable operator-requested drain state for cohort profile transitions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

_FIELDS = {
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
_REQUEST_ID = re.compile(r"[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class CohortTransitionDrainError(RuntimeError):
    """Transition-drain state is malformed, conflicting, or uncleared."""


@dataclass(frozen=True)
class CohortTransitionDrainSnapshot:
    """Validated durable state for one run-bound transition drain."""

    request_id: str
    origin_run_id: str
    run_id: str
    profile_fingerprint: str
    requested_at_utc: str
    activated_at_utc: str
    resume_count: int
    last_resumed_at_utc: str | None
    completed_at_utc: str | None
    status: str


class CohortTransitionDrain:
    """Persist and recover one identity-bound transition-drain request."""

    def __init__(
        self,
        *,
        path: Path,
        run_id: str,
        profile_fingerprint: str,
        now_fn: Callable[[], datetime],
    ) -> None:
        if not run_id.strip():
            raise ValueError("transition drain run identity is required")
        if not _SHA256.fullmatch(profile_fingerprint):
            raise ValueError("transition drain profile fingerprint is invalid")
        self._path = path
        self._run_id = run_id
        self._profile_fingerprint = profile_fingerprint
        self._now_fn = now_fn
        self._snapshot = _load(path) if path.exists() else None
        if self._snapshot is not None and self._snapshot.run_id != run_id:
            raise CohortTransitionDrainError("transition drain run identity differs")
        if (
            self._snapshot is not None
            and self._snapshot.profile_fingerprint != profile_fingerprint
        ):
            raise CohortTransitionDrainError(
                "transition drain profile identity differs"
            )

    @property
    def active(self) -> bool:
        """Return whether new entries must currently be withheld."""
        return self._snapshot is not None and self._snapshot.status == "active"

    @property
    def snapshot(self) -> CohortTransitionDrainSnapshot | None:
        """Return the current validated durable state, when one exists."""
        return self._snapshot

    def as_payload(self) -> dict[str, object]:
        """Return explicit current state for backend-authored telemetry."""
        snapshot = self._snapshot
        return {
            "status": "inactive" if snapshot is None else snapshot.status,
            "request_id": None if snapshot is None else snapshot.request_id,
            "origin_run_id": None if snapshot is None else snapshot.origin_run_id,
            "run_id": self._run_id,
            "profile_fingerprint": self._profile_fingerprint,
            "requested_at_utc": (
                None if snapshot is None else snapshot.requested_at_utc
            ),
            "activated_at_utc": (
                None if snapshot is None else snapshot.activated_at_utc
            ),
            "resume_count": 0 if snapshot is None else snapshot.resume_count,
            "last_resumed_at_utc": (
                None if snapshot is None else snapshot.last_resumed_at_utc
            ),
            "completed_at_utc": (
                None if snapshot is None else snapshot.completed_at_utc
            ),
        }

    def activate(
        self,
        *,
        request_id: str,
        requested_at_utc: str,
    ) -> CohortTransitionDrainSnapshot:
        """Persist a validated transition request before withholding entries."""
        if not _REQUEST_ID.fullmatch(request_id):
            raise CohortTransitionDrainError("transition drain request id is invalid")
        requested = _timestamp(requested_at_utc, "requested_at_utc")
        now = self._now_utc()
        if requested > now:
            raise CohortTransitionDrainError(
                "transition drain request is in the future"
            )
        if self._snapshot is not None:
            if (
                self._snapshot.status == "active"
                and self._snapshot.request_id == request_id
                and self._snapshot.requested_at_utc == requested.isoformat()
            ):
                return self._snapshot
            raise CohortTransitionDrainError(
                "a different transition drain already exists"
            )
        snapshot = CohortTransitionDrainSnapshot(
            request_id=request_id,
            origin_run_id=self._run_id,
            run_id=self._run_id,
            profile_fingerprint=self._profile_fingerprint,
            requested_at_utc=requested.isoformat(),
            activated_at_utc=now.isoformat(),
            resume_count=0,
            last_resumed_at_utc=None,
            completed_at_utc=None,
            status="active",
        )
        _write(self._path, snapshot)
        self._snapshot = snapshot
        return snapshot

    def complete(self) -> CohortTransitionDrainSnapshot:
        """Persist that the portfolio reached a flat and unowned boundary."""
        if self._snapshot is None or self._snapshot.status != "active":
            raise CohortTransitionDrainError("transition drain is not active")
        now = self._now_utc()
        activated = _timestamp(self._snapshot.activated_at_utc, "activated_at_utc")
        if now < activated:
            raise CohortTransitionDrainError(
                "transition drain completion precedes activation"
            )
        completed = replace(
            self._snapshot,
            completed_at_utc=now.isoformat(),
            status="completed",
        )
        _write(self._path, completed)
        self._snapshot = completed
        return completed

    def resume_for_run(self, run_id: str) -> CohortTransitionDrainSnapshot:
        """Bind an interrupted active drain to one explicit recovery process."""
        next_run = run_id.strip()
        if not next_run:
            raise CohortTransitionDrainError(
                "transition drain recovery run is required"
            )
        if self._snapshot is None or self._snapshot.status != "active":
            raise CohortTransitionDrainError("recovery requires an active drain")
        if next_run in {self._snapshot.origin_run_id, self._snapshot.run_id}:
            raise CohortTransitionDrainError(
                "transition drain recovery run must be new"
            )
        now = self._now_utc()
        boundary = _resume_boundary(self._snapshot)
        if now < boundary:
            raise CohortTransitionDrainError(
                "transition drain resume precedes prior state"
            )
        resumed = replace(
            self._snapshot,
            run_id=next_run,
            resume_count=self._snapshot.resume_count + 1,
            last_resumed_at_utc=now.isoformat(),
        )
        _write(self._path, resumed)
        self._run_id = next_run
        self._snapshot = resumed
        return resumed

    def _now_utc(self) -> datetime:
        value = self._now_fn()
        if value.tzinfo is None or value.utcoffset() is None:
            raise CohortTransitionDrainError("transition drain clock must be aware")
        return value.astimezone(timezone.utc)


def ensure_transition_drain_startable(path: Path) -> None:
    """Refuse a new live start while prior drain evidence remains uncleared."""
    if not path.exists():
        return
    _load(path)
    raise CohortTransitionDrainError(
        f"transition drain evidence remains; inspect and archive before live start: {path}"
    )


def load_transition_drain_snapshot(path: Path) -> CohortTransitionDrainSnapshot:
    """Load strict durable drain evidence for an explicit recovery decision."""
    return _load(path)


def verify_completed_transition_drain_archive(
    path: Path,
    *,
    expected_run_id: str,
    expected_profile_fingerprint: str,
) -> CohortTransitionDrainSnapshot:
    """Verify completed drain evidence against the exact prior run identity."""
    snapshot = _load(path)
    if snapshot.status != "completed":
        raise CohortTransitionDrainError("transition drain archive is not completed")
    if snapshot.run_id != expected_run_id:
        raise CohortTransitionDrainError(
            "transition drain archive run identity differs"
        )
    if snapshot.profile_fingerprint != expected_profile_fingerprint:
        raise CohortTransitionDrainError(
            "transition drain archive profile identity differs"
        )
    return snapshot


def archive_completed_transition_drain(
    *,
    path: Path,
    archive_root: Path,
    expected_run_id: str,
    now: datetime,
    confirmed: bool,
) -> Path:
    """Move completed drain evidence to recoverable history after confirmation."""
    snapshot = _load(path)
    if snapshot.status != "completed":
        raise CohortTransitionDrainError("transition drain is not completed")
    if snapshot.run_id != expected_run_id:
        raise CohortTransitionDrainError(
            "transition drain archive run identity differs"
        )
    observed = _aware_utc(now, "archive timestamp")
    timestamp = observed.strftime("%Y%m%dT%H%M%SZ")
    target = archive_root / f"transition_drain_{timestamp}_{snapshot.request_id}.json"
    if target.exists():
        raise CohortTransitionDrainError(f"transition drain archive exists: {target}")
    if not confirmed:
        return target
    original = path.read_bytes()
    archive_root.mkdir(parents=True, exist_ok=True)
    try:
        os.link(path, target)
    except OSError as exc:
        raise CohortTransitionDrainError(
            f"transition drain archive failed: {exc}"
        ) from exc
    if target.read_bytes() != original:
        raise CohortTransitionDrainError("transition drain archive verification failed")
    try:
        path.unlink()
    except OSError as exc:
        raise CohortTransitionDrainError(
            f"transition drain archived but active marker remains: {exc}"
        ) from exc
    return target


def _load(path: Path) -> CohortTransitionDrainSnapshot:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CohortTransitionDrainError(
            f"transition drain read failed: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise CohortTransitionDrainError("transition drain JSON is invalid") from exc
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise CohortTransitionDrainError("transition drain fields are invalid")
    if value.get("schema_version") != 1:
        raise CohortTransitionDrainError("transition drain schema is unsupported")
    request_id = _text(value, "request_id")
    fingerprint = _text(value, "profile_fingerprint")
    status = _text(value, "status")
    if not _REQUEST_ID.fullmatch(request_id):
        raise CohortTransitionDrainError("transition drain request id is invalid")
    if not _SHA256.fullmatch(fingerprint):
        raise CohortTransitionDrainError(
            "transition drain profile fingerprint is invalid"
        )
    if status not in {"active", "completed"}:
        raise CohortTransitionDrainError("transition drain status is invalid")
    requested = _timestamp(_text(value, "requested_at_utc"), "requested_at_utc")
    activated = _timestamp(_text(value, "activated_at_utc"), "activated_at_utc")
    origin_run_id = _text(value, "origin_run_id")
    run_id = _text(value, "run_id")
    resume_count = _resume_count(value.get("resume_count"))
    resumed = _optional_timestamp(
        value.get("last_resumed_at_utc"), "last_resumed_at_utc"
    )
    completed = _optional_timestamp(value.get("completed_at_utc"), "completed_at_utc")
    if (status == "completed") != (completed is not None):
        raise CohortTransitionDrainError("transition drain completion is inconsistent")
    if requested > activated or (completed is not None and activated > completed):
        raise CohortTransitionDrainError("transition drain chronology is invalid")
    _validate_resume_state(
        origin_run_id,
        run_id,
        resume_count,
        activated,
        resumed,
        completed,
    )
    return CohortTransitionDrainSnapshot(
        request_id=request_id,
        origin_run_id=origin_run_id,
        run_id=run_id,
        profile_fingerprint=fingerprint,
        requested_at_utc=requested.isoformat(),
        activated_at_utc=activated.isoformat(),
        resume_count=resume_count,
        last_resumed_at_utc=None if resumed is None else resumed.isoformat(),
        completed_at_utc=None if completed is None else completed.isoformat(),
        status=status,
    )


def _write(path: Path, snapshot: CohortTransitionDrainSnapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    payload = {"schema_version": 1, **asdict(snapshot)}
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise CohortTransitionDrainError(
            f"transition drain write failed: {exc}"
        ) from exc


def _text(values: dict[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CohortTransitionDrainError(f"transition drain {key} is invalid")
    return value.strip()


def _timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CohortTransitionDrainError(
            f"transition drain {label} is invalid"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CohortTransitionDrainError(f"transition drain {label} must be aware")
    return parsed.astimezone(timezone.utc)


def _aware_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CohortTransitionDrainError(f"transition drain {label} must be aware")
    return value.astimezone(timezone.utc)


def _optional_timestamp(value: object, label: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CohortTransitionDrainError(f"transition drain {label} is invalid")
    return _timestamp(value, label)


def _resume_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CohortTransitionDrainError("transition drain resume_count is invalid")
    return value


def _validate_resume_state(
    origin_run_id: str,
    run_id: str,
    resume_count: int,
    activated: datetime,
    resumed: datetime | None,
    completed: datetime | None,
) -> None:
    if resume_count == 0:
        if resumed is not None or run_id != origin_run_id:
            raise CohortTransitionDrainError("transition drain resume state is invalid")
        return
    if resumed is None or run_id == origin_run_id:
        raise CohortTransitionDrainError("transition drain resume state is invalid")
    if resumed < activated or (completed is not None and resumed > completed):
        raise CohortTransitionDrainError(
            "transition drain resume chronology is invalid"
        )


def _resume_boundary(snapshot: CohortTransitionDrainSnapshot) -> datetime:
    value = snapshot.last_resumed_at_utc or snapshot.activated_at_utc
    return _timestamp(value, "resume boundary")
