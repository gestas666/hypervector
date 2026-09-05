"""Shared errors and input validation for the SOL live engine."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

_IOC_NO_FILL_FRAGMENT = "could not immediately match against any resting orders"


class SolLiveEngineError(RuntimeError):
    """The live lifecycle encountered a technical execution fault."""


class SolEntryNotFilledError(SolLiveEngineError):
    """A definitive IOC acknowledgement left the venue safely flat."""


def is_ioc_no_fill_error(value: str | None) -> bool:
    """Recognize Hyperliquid's definitive immediate-or-cancel no-match text."""
    return bool(value and _IOC_NO_FILL_FRAGMENT in value.casefold())


def require_started(started: bool) -> None:
    """Reject lifecycle actions before successful preflight completion."""
    if not started:
        raise SolLiveEngineError("SOL live engine has not completed preflight")


def protective_stop_price(
    *,
    position_size_signed: float,
    entry_price: float,
    stop_bps: float,
) -> float:
    """Return the configured adverse stop price for one signed position."""
    distance = stop_bps / 10_000.0
    multiplier = 1.0 - distance if position_size_signed > 0.0 else 1.0 + distance
    return entry_price * multiplier


def resolve_decision_time_ms(
    value: int | None,
    now_fn: Callable[[], datetime],
) -> int:
    """Resolve an explicit or timezone-aware decision timestamp."""
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SolLiveEngineError("decision_time_ms must be a nonnegative integer")
        return value
    observed = now_fn()
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise SolLiveEngineError("now_fn must return a timezone-aware datetime")
    return int(observed.timestamp() * 1_000)
