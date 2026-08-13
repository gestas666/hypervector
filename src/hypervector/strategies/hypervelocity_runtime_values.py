"""Shared value validation for the Hypervelocity event runtime."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Literal

Direction = Literal["long", "short"]


def elapsed_seconds(start: str, end: str) -> float:
    """Return elapsed seconds between explicit UTC timestamps."""
    return (utc_timestamp(end, "end") - utc_timestamp(start, "start")).total_seconds()


def utc_timestamp(value: str, name: str) -> datetime:
    """Parse an ISO-8601 timestamp and require an explicit UTC offset."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must include an explicit UTC offset")
    return parsed


def require_positive(value: float | None, name: str) -> None:
    """Require a positive finite number."""
    if value is None or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be positive and finite")


def require_nonnegative(value: float, name: str) -> None:
    """Require a non-negative finite number."""
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be non-negative and finite")


def require_nonempty(value: str, name: str) -> None:
    """Require non-whitespace text."""
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")
