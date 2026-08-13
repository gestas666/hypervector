"""Frozen causal profit-lock policies shared by research and live execution."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math
from typing import Protocol

_BPS_DENOMINATOR = 10_000.0
_MINUTE_MS = 60_000


class CandleLike(Protocol):
    """Completed one-minute candle fields required by a profit lock."""

    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class ProfitLockPolicy:
    """One predeclared activation, floor, and peak-giveback mechanism."""

    policy_id: str
    activation_bps: float
    floor_bps: float
    trailing_giveback_bps: float


@dataclass(frozen=True)
class ProfitLockTrigger:
    """First completed-bar crossing of a previously active profit stop."""

    activation_timestamp_ms: int
    trigger_timestamp_ms: int
    reference_price: float
    stop_price: float
    best_completed_price: float


@dataclass(frozen=True)
class ProfitLockPathState:
    """Causal state of one policy after a completed candle prefix."""

    activation_timestamp_ms: int | None
    active_stop_price: float | None
    best_completed_price: float
    trigger: ProfitLockTrigger | None


POLICIES = (
    ProfitLockPolicy("a25_floor15_trail10", 25.0, 15.0, 10.0),
    ProfitLockPolicy("a40_floor15_trail20", 40.0, 15.0, 20.0),
    ProfitLockPolicy("a60_floor15_trail30", 60.0, 15.0, 30.0),
)


def evaluate_profit_lock_path(
    policy: ProfitLockPolicy,
    side: str,
    bars: Sequence[CandleLike],
    entry_price: float,
    *,
    activation_not_before_ms: int | None = None,
) -> ProfitLockPathState:
    """Evaluate one frozen lock using only prior completed-bar state."""
    _validate_inputs(policy, side, bars, entry_price, activation_not_before_ms)
    best = entry_price
    stop: float | None = None
    activation: int | None = None
    for candle in bars:
        if stop is not None and _crossed(side, candle, stop):
            reference = _trigger_reference(side, candle.open, stop)
            trigger = ProfitLockTrigger(
                activation or 0, candle.timestamp_ms, reference, stop, best
            )
            return ProfitLockPathState(activation, None, best, trigger)
        best = max(best, candle.high) if side == "long" else min(best, candle.low)
        favorable = _directional_bps(side, entry_price, best)
        allowed = (
            activation_not_before_ms is None
            or candle.timestamp_ms >= activation_not_before_ms
        )
        if activation is None and favorable >= policy.activation_bps and allowed:
            activation = candle.timestamp_ms
        if activation is not None:
            stop = _stop_price(policy, side, entry_price, best)
    return ProfitLockPathState(activation, stop, best, None)


def policy_declaration(policy: ProfitLockPolicy) -> dict[str, object]:
    """Serialize one immutable profit-lock declaration."""
    _validate_policy(policy)
    return {
        "policy_id": policy.policy_id,
        "activation_bps": policy.activation_bps,
        "floor_bps": policy.floor_bps,
        "trailing_giveback_bps": policy.trailing_giveback_bps,
    }


def _validate_inputs(
    policy: ProfitLockPolicy,
    side: str,
    bars: Sequence[CandleLike],
    entry_price: float,
    activation_not_before_ms: int | None,
) -> None:
    _validate_policy(policy)
    if side not in {"long", "short"}:
        raise ValueError("profit-lock side must be long or short")
    if not math.isfinite(entry_price) or entry_price <= 0.0:
        raise ValueError("profit-lock entry price must be positive and finite")
    if activation_not_before_ms is not None and (
        isinstance(activation_not_before_ms, bool)
        or activation_not_before_ms < 0
        or activation_not_before_ms % _MINUTE_MS
    ):
        raise ValueError("profit-lock activation boundary must align to a minute")
    prior = -1
    for candle in bars:
        _validate_candle(candle)
        if candle.timestamp_ms <= prior:
            raise ValueError("profit-lock candles must be strictly chronological")
        prior = candle.timestamp_ms


def _validate_policy(policy: ProfitLockPolicy) -> None:
    values = (policy.activation_bps, policy.floor_bps, policy.trailing_giveback_bps)
    if not policy.policy_id.strip() or any(
        not math.isfinite(value) or value <= 0.0 for value in values
    ):
        raise ValueError("profit-lock policy values must be positive and finite")


def _validate_candle(candle: CandleLike) -> None:
    prices = (candle.open, candle.high, candle.low, candle.close)
    valid = (
        not isinstance(candle.timestamp_ms, bool)
        and candle.timestamp_ms >= 0
        and candle.timestamp_ms % _MINUTE_MS == 0
        and all(math.isfinite(value) and value > 0.0 for value in prices)
        and candle.high >= max(candle.open, candle.close)
        and candle.low <= min(candle.open, candle.close)
        and candle.low <= candle.high
    )
    if not valid:
        raise ValueError("profit-lock candle is invalid")


def _stop_price(
    policy: ProfitLockPolicy,
    side: str,
    entry_price: float,
    best: float,
) -> float:
    floor = policy.floor_bps / _BPS_DENOMINATOR
    giveback = policy.trailing_giveback_bps / _BPS_DENOMINATOR
    if side == "long":
        return max(entry_price * (1.0 + floor), best * (1.0 - giveback))
    return min(entry_price * (1.0 - floor), best * (1.0 + giveback))


def _crossed(side: str, candle: CandleLike, stop: float) -> bool:
    return candle.low <= stop if side == "long" else candle.high >= stop


def _trigger_reference(side: str, open_price: float, stop: float) -> float:
    return min(open_price, stop) if side == "long" else max(open_price, stop)


def _directional_bps(side: str, entry: float, price: float) -> float:
    direction = 1.0 if side == "long" else -1.0
    return direction * (price / entry - 1.0) * _BPS_DENOMINATOR
