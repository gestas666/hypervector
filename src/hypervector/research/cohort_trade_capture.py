"""Completed-candle capture diagnostics for accepted cohort trades."""

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
_BPS_SCALE = 10_000.0
_ECONOMIC_ZERO_TOLERANCE_BPS = 1e-6


class CandleLike(Protocol):
    """Minimum completed-candle fields required for hold capture."""

    timestamp_ms: int
    high: float
    low: float


def build_completed_hold_capture(
    candles: Mapping[int, CandleLike],
    side: str,
    entry: Record,
    exit_leg: Record,
    *,
    economics: Record | None = None,
) -> dict[str, object]:
    """Measure completed-candle capture and optional after-cost economics."""
    direction = _direction(side)
    entry_ms = nonnegative_int(entry.get("venue_timestamp_ms"), "entry timestamp")
    exit_ms = nonnegative_int(exit_leg.get("venue_timestamp_ms"), "exit timestamp")
    if exit_ms <= entry_ms:
        raise ValueError("hold capture exit must occur after entry")
    entry_price = _positive(entry.get("price"), "entry price")
    exit_price = _positive(exit_leg.get("price"), "exit price")
    expected = _completed_timestamps(entry_ms, exit_ms)
    observed = tuple(candles[value] for value in expected if value in candles)
    if len(observed) != len(expected):
        capture = _missing_path(expected, observed)
        return _with_economics(capture, entry, economics)
    gross = _directional_bps(direction, entry_price, exit_price)
    if not observed:
        capture = _empty_path(gross)
        return _with_economics(capture, entry, economics)
    highest = max(entry_price, exit_price, *(value.high for value in observed))
    lowest = min(entry_price, exit_price, *(value.low for value in observed))
    favorable, adverse = _excursions(direction, entry_price, highest, lowest)
    capture = _resolved_path(expected, highest, lowest, favorable, adverse, gross)
    return _with_economics(capture, entry, economics)


def _with_economics(
    capture: dict[str, object], entry: Record, economics: Record | None
) -> dict[str, object]:
    if economics is None:
        return capture
    notional = _positive(entry.get("price"), "entry price") * _positive(
        entry.get("size"), "entry size"
    )
    fees = number(economics.get("fees_usd"), "lifecycle fees")
    funding = number(economics.get("funding_usd"), "lifecycle funding")
    net_pnl = number(economics.get("net_pnl_usd"), "lifecycle net PnL")
    if fees < 0.0:
        raise ValueError("lifecycle fees must be nonnegative")
    hurdle = (fees - funding) / notional * _BPS_SCALE
    net_return = net_pnl / notional * _BPS_SCALE
    authoritative_gross = (net_pnl + fees - funding) / notional * _BPS_SCALE
    gross = capture.get("realized_gross_return_bps")
    reconciliation_gap = (
        gross - authoritative_gross if isinstance(gross, float) else None
    )
    favorable = capture.get("maximum_favorable_excursion_bps")
    maximum_net = favorable - hurdle if isinstance(favorable, float) else None
    return {
        **capture,
        "observed_cost_hurdle_bps": hurdle,
        "maximum_net_excursion_bps": maximum_net,
        "realized_net_return_bps": net_return,
        "authoritative_gross_return_bps": authoritative_gross,
        "price_gross_reconciliation_gap_bps": reconciliation_gap,
        "economic_outcome": _economic_outcome(net_return, maximum_net),
        "economic_hurdle_basis": ("actual_fees_and_funding_over_filled_entry_notional"),
        "maximum_net_excursion_executable": False,
    }


def _economic_outcome(net_return: float, maximum_net: float | None) -> str:
    if net_return > _ECONOMIC_ZERO_TOLERANCE_BPS:
        return "profitable_after_costs"
    if abs(net_return) <= _ECONOMIC_ZERO_TOLERANCE_BPS:
        return "breakeven_after_costs"
    if maximum_net is None:
        return "completed_path_unavailable"
    if maximum_net <= _ECONOMIC_ZERO_TOLERANCE_BPS:
        return "never_cleared_observed_cost_hurdle"
    return "cleared_cost_hurdle_then_surrendered"


def _completed_timestamps(entry_ms: int, exit_ms: int) -> tuple[int, ...]:
    first_ms = ((entry_ms + _MINUTE_MS - 1) // _MINUTE_MS) * _MINUTE_MS
    last_ms = ((exit_ms - _MINUTE_MS) // _MINUTE_MS) * _MINUTE_MS
    if last_ms < first_ms:
        return ()
    return tuple(range(first_ms, last_ms + _MINUTE_MS, _MINUTE_MS))


def _missing_path(
    expected: tuple[int, ...],
    observed: tuple[CandleLike, ...],
) -> dict[str, object]:
    return {
        "status": "missing_data",
        "completed_bars_expected": len(expected),
        "completed_bars_observed": len(observed),
        "missing_candle_count": len(expected) - len(observed),
    }


def _empty_path(gross: float) -> dict[str, object]:
    return {
        "status": "no_completed_candles",
        "completed_bars": 0,
        "realized_gross_return_bps": gross,
        "maximum_favorable_excursion_bps": max(0.0, gross),
        "maximum_adverse_excursion_bps": max(0.0, -gross),
        "gross_mfe_capture_ratio": 1.0 if gross > 0.0 else None,
        "peak_giveback_bps": max(0.0, -gross),
    }


def _resolved_path(
    expected: tuple[int, ...],
    highest: float,
    lowest: float,
    favorable: float,
    adverse: float,
    gross: float,
) -> dict[str, object]:
    return {
        "status": "resolved",
        "completed_bars": len(expected),
        "first_completed_candle_timestamp_ms": expected[0],
        "last_completed_candle_timestamp_ms": expected[-1],
        "highest_observed_price": highest,
        "lowest_observed_price": lowest,
        "maximum_favorable_excursion_bps": favorable,
        "maximum_adverse_excursion_bps": adverse,
        "realized_gross_return_bps": gross,
        "gross_mfe_capture_ratio": gross / favorable if favorable > 0.0 else None,
        "peak_giveback_bps": favorable - gross,
    }


def _excursions(
    direction: float,
    entry_price: float,
    highest: float,
    lowest: float,
) -> tuple[float, float]:
    upward = (highest / entry_price - 1.0) * 10_000.0
    downward = (1.0 - lowest / entry_price) * 10_000.0
    return (
        (max(0.0, upward), max(0.0, downward))
        if direction > 0.0
        else (max(0.0, downward), max(0.0, upward))
    )


def _directional_bps(direction: float, entry: float, exit_price: float) -> float:
    return direction * (exit_price / entry - 1.0) * 10_000.0


def _direction(side: str) -> float:
    value = text(side, "hold capture side")
    if value not in {"long", "short"}:
        raise ValueError("hold capture side must be long or short")
    return 1.0 if value == "long" else -1.0


def _positive(value: object, label: str) -> float:
    parsed = number(value, label)
    if parsed <= 0.0:
        raise ValueError(f"{label} must be positive")
    return parsed
