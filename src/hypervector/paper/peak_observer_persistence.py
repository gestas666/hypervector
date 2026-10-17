"""Durable restoration for report-only peak observer state."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from hypervector.paper.peak_protection_observer import (
    PEAK_OBSERVER_SCHEMA,
    PeakDirection,
    PeakObserverState,
)


class PeakObserverRestoreError(ValueError):
    """Raised when matching durable observer state is malformed."""


def load_peak_observer_state(
    ledger_path: Path,
    *,
    run_id: str,
    candidate_id: str,
) -> PeakObserverState | None:
    """Restore the latest complete matching observer state from JSONL."""
    if not ledger_path.exists():
        return None
    latest: dict[str, object] | None = None
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            if not raw.endswith("\n") and not _is_json(raw):
                continue  # torn final line from a crash; the next append repairs it
            record = _record(raw, line_number)
            if _matches(record, run_id=run_id, candidate_id=candidate_id):
                latest = record
    if latest is None:
        return None
    _expect_schema(latest)
    if not _boolean(latest, "observer_active"):
        return None
    return _state(latest)


def _is_json(raw: str) -> bool:
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        return False
    return True


def _record(raw: str, line_number: int) -> dict[str, object]:
    try:
        value: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PeakObserverRestoreError(
            f"observer ledger line {line_number} is invalid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise PeakObserverRestoreError(
            f"observer ledger line {line_number} is not an object"
        )
    return cast(dict[str, object], value)


def _matches(
    record: dict[str, object],
    *,
    run_id: str,
    candidate_id: str,
) -> bool:
    action = record.get("action")
    return (
        record.get("run_id") == run_id
        and record.get("candidate_id") == candidate_id
        and isinstance(action, str)
        and action.startswith("peak_observer_")
    )


def _expect_schema(record: dict[str, object]) -> None:
    if record.get("observer_schema") != PEAK_OBSERVER_SCHEMA:
        raise PeakObserverRestoreError(
            f"observer_schema must be {PEAK_OBSERVER_SCHEMA!r}"
        )


def _state(record: dict[str, object]) -> PeakObserverState:
    direction = _text(record, "position_direction")
    if direction not in {"long", "short"}:
        raise PeakObserverRestoreError("position_direction must be long|short")
    return PeakObserverState(
        direction=cast(PeakDirection, direction),
        quantity=_positive(record, "position_quantity"),
        entry_price=_positive(record, "position_entry_price"),
        position_started_at=_timestamp(record, "position_started_at"),
        coverage_complete_since_entry=_boolean(
            record,
            "coverage_complete_since_entry",
        ),
        peak_margin_pct=_nonnegative(record, "peak_margin_pct"),
        locked_margin_pct=_optional_number(record, "locked_margin_pct"),
        hypothetical_stop_price=_optional_number(
            record,
            "hypothetical_stop_price",
        ),
        last_sample_at=_optional_timestamp(record, "last_sample_at"),
        last_update_at=_optional_timestamp(record, "last_update_at"),
        trigger_unpriced_at=_optional_timestamp(record, "trigger_unpriced_at"),
        hypothetical_exit_at=_optional_timestamp(record, "hypothetical_exit_at"),
        hypothetical_exit_price=_optional_number(
            record,
            "hypothetical_exit_price",
        ),
        hypothetical_exit_fee_usd=_optional_number(
            record,
            "hypothetical_exit_fee_usd",
        ),
    )


def _text(record: dict[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise PeakObserverRestoreError(f"{field} must be non-empty text")
    return value


def _boolean(record: dict[str, object], field: str) -> bool:
    value = record.get(field)
    if not isinstance(value, bool):
        raise PeakObserverRestoreError(f"{field} must be boolean")
    return value


def _number(record: dict[str, object], field: str) -> float:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PeakObserverRestoreError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise PeakObserverRestoreError(f"{field} must be finite")
    return number


def _positive(record: dict[str, object], field: str) -> float:
    value = _number(record, field)
    if value <= 0.0:
        raise PeakObserverRestoreError(f"{field} must be positive")
    return value


def _nonnegative(record: dict[str, object], field: str) -> float:
    value = _number(record, field)
    if value < 0.0:
        raise PeakObserverRestoreError(f"{field} must be non-negative")
    return value


def _optional_number(record: dict[str, object], field: str) -> float | None:
    if record.get(field) is None:
        return None
    return _number(record, field)


def _timestamp(record: dict[str, object], field: str) -> str:
    value = _text(record, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PeakObserverRestoreError(f"{field} must be ISO-8601") from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise PeakObserverRestoreError(f"{field} must use UTC")
    return value


def _optional_timestamp(record: dict[str, object], field: str) -> str | None:
    if record.get(field) is None:
        return None
    return _timestamp(record, field)
