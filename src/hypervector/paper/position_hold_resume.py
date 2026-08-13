"""Recover a durable position-open clock from shadow-ledger evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from hypervector.paper.position_math import normalized_position_quantity


@dataclass(frozen=True)
class PositionHoldResume:
    """Original open timestamp and configured maximum hold for one position."""

    position_opened_at: str | None
    maximum_hold_seconds: float | None


def recover_position_hold_resume(
    rows: list[dict[str, object]],
    *,
    final_position_qty: float,
) -> PositionHoldResume:
    """Recover hold state without treating a restart as a new entry."""
    if normalized_position_quantity(final_position_qty) == 0.0:
        return PositionHoldResume(None, None)
    opened_at = _current_position_opened_at(rows)
    maximum_hold = _configured_maximum_hold(rows)
    if maximum_hold is not None and opened_at is None:
        raise ValueError("open maximum-hold position has no position-open timestamp")
    return PositionHoldResume(opened_at, maximum_hold)


def _current_position_opened_at(rows: list[dict[str, object]]) -> str | None:
    opened_at: str | None = None
    previous = 0.0
    for row in rows:
        position = _number(row.get("position_qty"))
        if position is None:
            continue
        position = normalized_position_quantity(position)
        if position == 0.0:
            opened_at = None
            previous = 0.0
            continue
        explicit = row.get("position_opened_at")
        if isinstance(explicit, str) and explicit:
            opened_at = _validated_utc(explicit)
        elif previous == 0.0 or previous * position < 0.0:
            opened_at = _entry_timestamp(row)
        previous = position
    return opened_at


def _entry_timestamp(row: dict[str, object]) -> str | None:
    if row.get("action") not in {"enter_long", "enter_short"}:
        return None
    value = row.get("feed_ts")
    return _validated_utc(value) if isinstance(value, str) and value else None


def _configured_maximum_hold(rows: list[dict[str, object]]) -> float | None:
    for row in reversed(rows):
        direct = _positive_number(row.get("maximum_hold_seconds"))
        if direct is not None:
            return direct
        spec = row.get("portfolio_spec")
        if not isinstance(spec, dict):
            continue
        policy = spec.get("regime_policy")
        if isinstance(policy, dict):
            configured = _positive_number(policy.get("maximum_hold_seconds"))
            if configured is not None:
                return configured
    return None


def _validated_utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("position-open timestamp must be timezone-aware")
    if parsed.utcoffset().total_seconds() != 0.0:
        raise ValueError("position-open timestamp must be UTC")
    return value


def _positive_number(value: object) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0.0 else None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None
