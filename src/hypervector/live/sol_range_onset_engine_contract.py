"""Shared errors and input validation for the SOL live engine."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import Enum

from hypervector.live.cohort_execution_plan import BoundExecutionPlan
from hypervector.live.hyperliquid_protocol import HyperliquidOrderAck

_IOC_NO_FILL_FRAGMENT = "could not immediately match against any resting orders"


class StopRaiseOutcome(Enum):
    """A stop raise that needed no venue call; falsy because nothing was raised."""

    ALREADY_AT_TARGET = "already_at_target"

    def __bool__(self) -> bool:
        return False


# The owned venue stop already rests at or beyond the wire-rounded raise target.
STOP_ALREADY_AT_TARGET = StopRaiseOutcome.ALREADY_AT_TARGET


def stop_rests_at_or_beyond(current: float, target: float, size: float) -> bool:
    """Return whether a stop trigger is at least as protective as the target."""
    return current >= target if size > 0.0 else current <= target


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


def is_expected_ioc_no_fill(
    plan: BoundExecutionPlan,
    ack: HyperliquidOrderAck,
) -> bool:
    """Recognize only Hyperliquid's definitive IOC no-match acknowledgement."""
    return bool(
        plan.entry_liquidity == "taker_ioc"
        and not ack.accepted
        and ack.oid is None
        and ack.status == "error"
        and ack.error is not None
        and is_ioc_no_fill_error(ack.error)
    )
