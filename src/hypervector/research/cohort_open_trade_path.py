"""Completed-candle excursion evidence for one open cohort lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from hypervector.research.cohort_live_audit_values import (
    nonnegative_int,
    number,
    text,
)

Record = Mapping[str, object]
_MINUTE_MS = 60_000


class _CandleLike(Protocol):
    timestamp_ms: int
    high: float
    low: float
    close: float


def build_open_trade_path(
    candles: Mapping[int, _CandleLike],
    side: str,
    entry: Record,
    marked_economics: Record,
    as_of_ms: int,
) -> dict[str, object]:
    """Project causal completed-candle excursion and current marked giveback."""
    direction = _direction(side)
    entry_ms = nonnegative_int(entry.get("venue_timestamp_ms"), "entry timestamp")
    entry_price = _positive(entry.get("price"), "entry price")
    mark_price = _positive(marked_economics.get("mark_price"), "mark price")
    first_ms = _next_minute(entry_ms)
    eligible = sorted(
        (
            candle
            for candle in candles.values()
            if first_ms <= candle.timestamp_ms
            and candle.timestamp_ms + _MINUTE_MS <= as_of_ms
        ),
        key=lambda candle: candle.timestamp_ms,
    )
    if not eligible:
        return _unavailable_path(direction, entry_price, mark_price)
    highest = max(candle.high for candle in eligible)
    lowest = min(candle.low for candle in eligible)
    current = _directional_bps(direction, entry_price, mark_price)
    favorable, adverse = _excursions(direction, entry_price, highest, lowest)
    return {
        "status": "observed",
        "completed_bars": len(eligible),
        "first_timestamp_ms": eligible[0].timestamp_ms,
        "last_timestamp_ms": eligible[-1].timestamp_ms,
        "highest_price": highest,
        "lowest_price": lowest,
        "current_directional_return_bps": current,
        "maximum_favorable_excursion_bps": favorable,
        "maximum_adverse_excursion_bps": adverse,
        "peak_giveback_bps": max(0.0, favorable - current),
    }


def build_open_trade_extension_path(
    candles: Mapping[int, _CandleLike],
    side: str,
    *,
    soft_deadline_ms: int,
    marked_economics: Record,
    as_of_ms: int,
) -> dict[str, object]:
    """Measure incremental path strictly after a configured soft deadline."""
    direction = _direction(side)
    boundary = nonnegative_int(soft_deadline_ms, "soft deadline")
    observed = nonnegative_int(as_of_ms, "path observation timestamp")
    if observed < boundary:
        return _extension_unavailable("pending_soft_deadline", boundary)
    completed_at_boundary = [
        candle
        for candle in candles.values()
        if candle.timestamp_ms + _MINUTE_MS <= boundary
    ]
    if not completed_at_boundary:
        return _extension_unavailable("unavailable_boundary_close", boundary)
    baseline = max(completed_at_boundary, key=lambda candle: candle.timestamp_ms)
    baseline_price = _positive(baseline.close, "soft boundary close")
    mark_price = _positive(marked_economics.get("mark_price"), "mark price")
    eligible = _completed_candles(candles, _next_minute(boundary), observed)
    current = _directional_bps(direction, baseline_price, mark_price)
    if not eligible:
        return _extension_waiting(boundary, baseline, baseline_price, current)
    highest = max(candle.high for candle in eligible)
    lowest = min(candle.low for candle in eligible)
    favorable, adverse = _excursions(direction, baseline_price, highest, lowest)
    return {
        "status": "observed",
        "boundary_timestamp_ms": boundary,
        "baseline_timestamp_ms": baseline.timestamp_ms,
        "baseline_price": baseline_price,
        "completed_bars": len(eligible),
        "first_timestamp_ms": eligible[0].timestamp_ms,
        "last_timestamp_ms": eligible[-1].timestamp_ms,
        "highest_price": highest,
        "lowest_price": lowest,
        "current_directional_return_bps": current,
        "maximum_favorable_excursion_bps": favorable,
        "maximum_adverse_excursion_bps": adverse,
        "peak_giveback_bps": max(0.0, favorable - current),
    }


def _completed_candles(
    candles: Mapping[int, _CandleLike], first_ms: int, as_of_ms: int
) -> list[_CandleLike]:
    return sorted(
        (
            candle
            for candle in candles.values()
            if first_ms <= candle.timestamp_ms
            and candle.timestamp_ms + _MINUTE_MS <= as_of_ms
        ),
        key=lambda candle: candle.timestamp_ms,
    )


def _extension_unavailable(status: str, boundary_ms: int) -> dict[str, object]:
    return {
        "status": status,
        "boundary_timestamp_ms": boundary_ms,
        "baseline_timestamp_ms": None,
        "baseline_price": None,
        "completed_bars": 0,
        "first_timestamp_ms": None,
        "last_timestamp_ms": None,
        "highest_price": None,
        "lowest_price": None,
        "current_directional_return_bps": None,
        "maximum_favorable_excursion_bps": None,
        "maximum_adverse_excursion_bps": None,
        "peak_giveback_bps": None,
    }


def _extension_waiting(
    boundary_ms: int,
    baseline: _CandleLike,
    baseline_price: float,
    current: float,
) -> dict[str, object]:
    output = _extension_unavailable("awaiting_completed_bar", boundary_ms)
    output.update(
        {
            "baseline_timestamp_ms": baseline.timestamp_ms,
            "baseline_price": baseline_price,
            "current_directional_return_bps": current,
        }
    )
    return output


def _direction(side: str) -> float:
    value = text(side, "open trade side")
    if value not in {"long", "short"}:
        raise ValueError("open trade side must be long or short")
    return 1.0 if value == "long" else -1.0


def _positive(value: object, label: str) -> float:
    parsed = number(value, label)
    if parsed <= 0.0:
        raise ValueError(f"{label} must be positive")
    return parsed


def _next_minute(timestamp_ms: int) -> int:
    return ((timestamp_ms + _MINUTE_MS - 1) // _MINUTE_MS) * _MINUTE_MS


def _directional_bps(direction: float, entry: float, price: float) -> float:
    return direction * (price / entry - 1.0) * 10_000.0


def _excursions(
    direction: float,
    entry: float,
    highest: float,
    lowest: float,
) -> tuple[float, float]:
    favorable_price = highest if direction > 0.0 else lowest
    adverse_price = lowest if direction > 0.0 else highest
    favorable = max(0.0, _directional_bps(direction, entry, favorable_price))
    adverse = max(0.0, -_directional_bps(direction, entry, adverse_price))
    return favorable, adverse


def _unavailable_path(
    direction: float,
    entry_price: float,
    mark_price: float,
) -> dict[str, object]:
    return {
        "status": "unavailable",
        "completed_bars": 0,
        "first_timestamp_ms": None,
        "last_timestamp_ms": None,
        "highest_price": None,
        "lowest_price": None,
        "current_directional_return_bps": _directional_bps(
            direction, entry_price, mark_price
        ),
        "maximum_favorable_excursion_bps": None,
        "maximum_adverse_excursion_bps": None,
        "peak_giveback_bps": None,
    }
