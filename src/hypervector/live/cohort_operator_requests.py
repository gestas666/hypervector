"""Atomic headless request publication using the backend's validation contract."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
from uuid import uuid4

from hypervector.live.cohort_operator_commands import validate_operator_request


def build_request(
    *,
    run_id: str,
    profile_fingerprint: str,
    action: str,
    symbol: str,
    provider: str | None = None,
    side: str | None = None,
    settings: dict[str, object] | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Compose a validated request; publication and execution are separate actions."""
    observed = now or datetime.now(UTC)
    if observed.utcoffset() is None:
        raise ValueError("operator request clock must be timezone-aware")
    request = {
        "schema_version": 1,
        "request_id": uuid4().hex,
        "run_id": run_id,
        "profile_fingerprint": profile_fingerprint,
        "created_at_utc": observed.isoformat(),
        "action": action,
        "symbol": symbol,
        "provider": provider,
        "side": side,
        "settings": settings,
    }
    validate_operator_request(
        str(request["request_id"]),
        request,
        run_id=run_id,
        profile_fingerprint=profile_fingerprint,
        now=observed,
        maximum_age_seconds=60.0,
    )
    return request


def publish_request(
    root: Path, request: dict[str, object], *, now: datetime | None = None
) -> Path:
    """Publish a complete request atomically without overwriting an existing ID."""
    validate_operator_request(
        str(request.get("request_id")),
        request,
        run_id=str(request.get("run_id")),
        profile_fingerprint=str(request.get("profile_fingerprint")),
        now=now or datetime.now(UTC),
        maximum_age_seconds=60.0,
    )
    pending = root / "pending"
    if not pending.is_dir():
        raise ValueError(f"operator inbox is unavailable: {pending}")
    request_id = str(request["request_id"])
    target = pending / f"{request_id}.json"
    temporary = pending / f".{request_id}.{uuid4().hex}.tmp"
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            os.chmod(temporary, 0o600)
            stream.write(json.dumps(request, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
