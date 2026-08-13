"""Report-only completed-candle follow-through after a live cohort entry."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from hypervector.research.cohort_live_audit_values import (
    nonnegative_int,
    number,
    text,
)

Record = Mapping[str, object]
_MINUTE_MS = 60_000


class CandleLike(Protocol):
    """Minimum completed-candle fields required for follow-through paths."""

    timestamp_ms: int
    high: float
    low: float
    close: float


def build_entry_followthrough_paths(
    candles: Mapping[int, CandleLike],
    side: str,
    entry: Record,
    protective_stop: Record | None,
    horizons_minutes: Sequence[int],
) -> dict[str, object]:
    """Measure partial or resolved paths from an authoritative entry fill."""
    direction = _direction(side)
    entry_ms = nonnegative_int(entry.get("venue_timestamp_ms"), "entry timestamp")
    entry_price = _positive(entry.get("price"), "entry price")
    first_ms = _next_minute(entry_ms)
    horizons = _validated_horizons(horizons_minutes)
    trigger = _stop_trigger(protective_stop)
    return {
        str(horizon): _path(
            candles,
            direction,
            entry_price,
            first_ms,
            horizon,
            trigger,
        )
        for horizon in horizons
    }


def _path(
    candles: Mapping[int, CandleLike],
    direction: float,
    entry_price: float,
    first_ms: int,
    horizon: int,
    trigger: float | None,
) -> dict[str, object]:
    expected = tuple(first_ms + offset * _MINUTE_MS for offset in range(horizon))
    observed = _contiguous_prefix(candles, expected)
    status = _path_status(candles, expected, observed)
    if not observed:
        return _empty_path(status, horizon, trigger)
    highest = max(candle.high for candle in observed)
    lowest = min(candle.low for candle in observed)
    close_bps = _directional_bps(direction, entry_price, observed[-1].close)
    favorable, adverse = _excursions(direction, entry_price, highest, lowest)
    first_stop = _first_stop_cross(observed, direction, trigger)
    return {
        "status": status,
        "bars_observed": len(observed),
        "bars_required": horizon,
        "completion_pct": len(observed) / horizon * 100.0,
        "first_candle_timestamp_ms": observed[0].timestamp_ms,
        "last_candle_timestamp_ms": observed[-1].timestamp_ms,
        "last_close_price": observed[-1].close,
        "lowest_price": lowest,
        "highest_price": highest,
        "directional_close_return_bps": close_bps,
        "favorable_excursion_bps": favorable,
        "adverse_excursion_bps": adverse,
        "interpretation": _interpretation(close_bps),
        "protective_stop_trigger_price": trigger,
        "protective_stop_price_crossed": (
            None if trigger is None else first_stop is not None
        ),
        "first_stop_price_cross_timestamp_ms": first_stop,
    }


def _contiguous_prefix(
    candles: Mapping[int, CandleLike], expected: Sequence[int]
) -> tuple[CandleLike, ...]:
    output: list[CandleLike] = []
    for timestamp_ms in expected:
        candle = candles.get(timestamp_ms)
        if candle is None:
            break
        output.append(candle)
    return tuple(output)


def _path_status(
    candles: Mapping[int, CandleLike],
    expected: Sequence[int],
    observed: Sequence[CandleLike],
) -> str:
    if len(observed) == len(expected):
        return "resolved"
    next_expected = expected[len(observed)]
    if not candles or max(candles) < next_expected:
        return "censored"
    return "missing_data"


def _empty_path(status: str, horizon: int, trigger: float | None) -> dict[str, object]:
    return {
        "status": status,
        "bars_observed": 0,
        "bars_required": horizon,
        "completion_pct": 0.0,
        "first_candle_timestamp_ms": None,
        "last_candle_timestamp_ms": None,
        "last_close_price": None,
        "lowest_price": None,
        "highest_price": None,
        "directional_close_return_bps": None,
        "favorable_excursion_bps": None,
        "adverse_excursion_bps": None,
        "interpretation": None,
        "protective_stop_trigger_price": trigger,
        "protective_stop_price_crossed": None if trigger is None else False,
        "first_stop_price_cross_timestamp_ms": None,
    }


def _first_stop_cross(
    candles: Sequence[CandleLike], direction: float, trigger: float | None
) -> int | None:
    if trigger is None:
        return None
    for candle in candles:
        crossed = candle.low <= trigger if direction > 0.0 else candle.high >= trigger
        if crossed:
            return candle.timestamp_ms
    return None


def _validated_horizons(values: Sequence[int]) -> tuple[int, ...]:
    horizons = tuple(values)
    if not horizons or len(horizons) != len(set(horizons)):
        raise ValueError("entry follow-through horizons must be unique and non-empty")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in horizons
    ):
        raise ValueError("entry follow-through horizons must be positive integers")
    return tuple(sorted(horizons))


def _direction(side: str) -> float:
    value = text(side, "entry follow-through side")
    if value not in {"long", "short"}:
        raise ValueError("entry follow-through side must be long or short")
    return 1.0 if value == "long" else -1.0


def _positive(value: object, label: str) -> float:
    parsed = number(value, label)
    if parsed <= 0.0:
        raise ValueError(f"{label} must be positive")
    return parsed


def _stop_trigger(protective_stop: Record | None) -> float | None:
    if protective_stop is None:
        return None
    return _positive(protective_stop.get("trigger_price"), "protective stop trigger")


def _next_minute(timestamp_ms: int) -> int:
    return ((timestamp_ms + _MINUTE_MS - 1) // _MINUTE_MS) * _MINUTE_MS


def _directional_bps(direction: float, entry: float, price: float) -> float:
    return direction * (price / entry - 1.0) * 10_000.0


def _excursions(
    direction: float, entry: float, highest: float, lowest: float
) -> tuple[float, float]:
    upward = (highest / entry - 1.0) * 10_000.0
    downward = (1.0 - lowest / entry) * 10_000.0
    favorable = upward if direction > 0.0 else downward
    adverse = downward if direction > 0.0 else upward
    return max(0.0, favorable), max(0.0, adverse)


def _interpretation(directional_close_return_bps: float) -> str:
    if directional_close_return_bps > 0.0:
        return "continued_original_direction"
    if directional_close_return_bps < 0.0:
        return "reversed_against_original_direction"
    return "unchanged"
