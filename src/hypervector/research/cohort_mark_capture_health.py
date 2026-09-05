"""Fail-explicit health evidence for the report-only HIP-3 mark recorder."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from pathlib import Path

_SYMBOLS = ("xyz:SP500", "xyz:SPCX")
_SOURCE = "hyperliquid_info_metaAndAssetCtxs"


@dataclass(frozen=True)
class MarkCaptureHealth:
    """Material recorder state plus exact mutable-source evidence."""

    status: dict[str, object]
    evidence: dict[str, object] | None


def load_index_mark_capture_health(
    path: Path,
    *,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> MarkCaptureHealth:
    """Load one exact recorder status or report its absence explicitly."""
    _validate_time_inputs(observed_at, maximum_age_seconds)
    if not path.exists():
        return MarkCaptureHealth(_unavailable("unavailable_missing"), None)
    raw = path.read_bytes()
    payload = _mapping(json.loads(raw), "index mark recorder status")
    _validate_contract(payload)
    age_seconds = _status_age(payload, observed_at)
    evidence = _evidence(path, raw, payload, age_seconds)
    event_type = _text(payload.get("event_type"), "recorder event type")
    if event_type == "hip3_mark_recorder_stopped":
        return MarkCaptureHealth(_unavailable("unavailable_stopped"), evidence)
    if age_seconds > maximum_age_seconds:
        return MarkCaptureHealth(_unavailable("unavailable_stale"), evidence)
    state = "starting" if event_type == "hip3_mark_recorder_started" else "healthy"
    return MarkCaptureHealth(_available(state, payload), evidence)


def _validate_time_inputs(observed_at: datetime, maximum_age_seconds: float) -> None:
    if observed_at.tzinfo is None:
        raise ValueError("mark recorder observation time must include a timezone")
    if not math.isfinite(maximum_age_seconds) or maximum_age_seconds <= 0.0:
        raise ValueError("maximum mark recorder age must be positive and finite")


def _validate_contract(payload: Mapping[str, object]) -> None:
    expected = {
        "symbols": list(_SYMBOLS),
        "source": _SOURCE,
        "execution_authority": "none",
        "report_only": True,
        "signing_client_constructed": False,
        "orders_supported": False,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ValueError(f"index mark recorder has invalid {field}")
    event_type = _text(payload.get("event_type"), "recorder event type")
    allowed = {
        "hip3_mark_recorder_started",
        "hip3_mark_recorder_heartbeat",
        "hip3_mark_recorder_stopped",
    }
    if event_type not in allowed:
        raise ValueError("index mark recorder event type is invalid")
    _validate_progress(payload)


def _validate_progress(payload: Mapping[str, object]) -> None:
    polls = _nonnegative_integer(payload.get("polls"), "recorder polls")
    rows = _mapping(payload.get("rows_by_symbol"), "recorder rows by symbol")
    if set(rows) != set(_SYMBOLS):
        raise ValueError("index mark recorder row identities are invalid")
    for symbol in _SYMBOLS:
        count = _nonnegative_integer(rows.get(symbol), f"{symbol} recorder rows")
        if count > polls:
            raise ValueError("index mark recorder rows cannot exceed polls")
    poll_seconds = payload.get("poll_seconds")
    if isinstance(poll_seconds, bool) or not isinstance(poll_seconds, (int, float)):
        raise ValueError("index mark recorder cadence must be numeric")
    if not math.isfinite(float(poll_seconds)) or not 0.0 < poll_seconds <= 5.0:
        raise ValueError("index mark recorder cadence must be within five seconds")


def _status_age(payload: Mapping[str, object], observed_at: datetime) -> float:
    recorded_ns = _positive_integer(payload.get("recorded_at_ns"), "recorder timestamp")
    recorded_at = datetime.fromtimestamp(recorded_ns / 1_000_000_000, UTC)
    age_seconds = (observed_at.astimezone(UTC) - recorded_at).total_seconds()
    if age_seconds < 0.0:
        raise ValueError("index mark recorder status is in the future")
    return age_seconds


def _available(state: str, payload: Mapping[str, object]) -> dict[str, object]:
    return {
        "status": state,
        "symbols": list(_SYMBOLS),
        "source": _SOURCE,
        "poll_seconds": payload["poll_seconds"],
        "execution_authority": "none",
        "report_only": True,
        "orders_supported": False,
    }


def _unavailable(status: str) -> dict[str, object]:
    return {
        "status": status,
        "symbols": list(_SYMBOLS),
        "source": _SOURCE,
        "execution_authority": "none",
        "report_only": True,
        "orders_supported": False,
    }


def _evidence(
    path: Path,
    raw: bytes,
    payload: Mapping[str, object],
    age_seconds: float,
) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
        "event_type": payload["event_type"],
        "recorded_at_ns": payload["recorded_at_ns"],
        "age_seconds": age_seconds,
        "polls": payload["polls"],
        "rows_by_symbol": dict(_mapping(payload["rows_by_symbol"], "recorder rows")),
    }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _positive_integer(value: object, label: str) -> int:
    output = _nonnegative_integer(value, label)
    if output == 0:
        raise ValueError(f"{label} must be positive")
    return output
