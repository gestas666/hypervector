"""Report-only open-profit protection and giveback arithmetic."""

from __future__ import annotations

from collections.abc import Mapping
import math

from hypervector.research.cohort_live_audit_values import number

Record = Mapping[str, object]
_MONEY_TOLERANCE = 0.000_005


def build_open_profit_protection(
    side: str,
    entry: Record,
    protective_stop: Record | None,
    marked_economics: Record,
) -> dict[str, object]:
    """Estimate current and stop-exit net values without execution authority."""
    if protective_stop is None:
        return {
            "status": "unavailable",
            "reason": "protective_stop_unavailable",
        }
    direction = _direction(side)
    entry_price = _positive(entry.get("price"), "entry price")
    size = _positive(entry.get("size"), "entry size")
    mark_price = _positive(marked_economics.get("mark_price"), "mark price")
    stop_price = _positive(protective_stop.get("trigger_price"), "stop price")
    entry_fee = _nonnegative(marked_economics.get("fees_usd"), "entry fee")
    funding = number(marked_economics.get("funding_usd"), "funding")
    marked_net = number(
        marked_economics.get("active_lifecycle_marked_net_pnl_usd"),
        "marked net PnL",
    )
    fee_rate = entry_fee / (entry_price * size)
    current_gross = direction * (mark_price - entry_price) * size
    _validate_marked_net(marked_net, current_gross - entry_fee + funding)
    current_exit_fee = mark_price * size * fee_rate
    stop_exit_fee = stop_price * size * fee_rate
    current_net = marked_net - current_exit_fee
    stop_gross = direction * (stop_price - entry_price) * size
    stop_net = stop_gross - entry_fee - stop_exit_fee + funding
    giveback = current_net - stop_net
    return {
        "status": _protection_status(current_net, stop_net, giveback),
        "reported_marked_net_pnl_usd": marked_net,
        "estimated_exit_now_net_usd": current_net,
        "estimated_stop_net_usd": stop_net,
        "marked_to_stop_giveback_usd": giveback,
        "protected_profit_fraction": _protected_fraction(current_net, stop_net),
        "stop_distance_from_mark_bps": (
            direction * (mark_price - stop_price) / mark_price * 10_000.0
        ),
        "measured_entry_fee_rate_bps": fee_rate * 10_000.0,
        "estimated_current_exit_fee_usd": current_exit_fee,
        "estimated_stop_exit_fee_usd": stop_exit_fee,
        "method": "measured_entry_fee_rate_no_future_funding_or_slippage",
    }


def _direction(side: str) -> float:
    if side == "long":
        return 1.0
    if side == "short":
        return -1.0
    raise ValueError("open-profit side must be long or short")


def _positive(value: object, label: str) -> float:
    parsed = number(value, label)
    if parsed <= 0.0:
        raise ValueError(f"{label} must be positive")
    return parsed


def _nonnegative(value: object, label: str) -> float:
    parsed = number(value, label)
    if parsed < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return parsed


def _validate_marked_net(observed: float, expected: float) -> None:
    if not math.isclose(observed, expected, abs_tol=_MONEY_TOLERANCE):
        raise ValueError("marked net PnL does not reconcile to entry economics")


def _protection_status(current: float, stop: float, giveback: float) -> str:
    if current <= 0.0:
        return "no_open_profit"
    if stop <= 0.0:
        return "open_profit_unprotected"
    if giveback > _MONEY_TOLERANCE:
        return "partial_profit_locked"
    return "current_profit_locked"


def _protected_fraction(current: float, stop: float) -> float | None:
    if current <= 0.0:
        return None
    return min(1.0, max(0.0, stop) / current)
