"""Report-only profit-lock evidence for exact config-bound forward paths."""

from __future__ import annotations

from collections.abc import Mapping
import math

from hypervector.research.cohort_live_audit_values import (
    mapping_list,
    nonnegative_int,
    number,
    text,
)
from hypervector.research.cohort_open_profit_lock_challenger import (
    build_open_profit_lock_challenger,
)
from hypervector.research.cohort_profit_lock_policy import CandleLike

Record = Mapping[str, object]
_BPS = 10_000.0
_RECONCILIATION_TOLERANCE = 0.000_001


def build_policy_forward_profit_lock_report(
    candles: Mapping[int, CandleLike],
    exact_depth_report: Record,
    *,
    taker_fee_rate: float,
) -> dict[str, object]:
    """Evaluate frozen causal locks without changing the native exit policy."""
    fee_rate = _fee_rate(taker_fee_rate)
    attempts = mapping_list(
        exact_depth_report.get("latest_attempts"), "exact latest attempts"
    )
    results = [_lifecycle(candles, attempt, fee_rate) for attempt in attempts]
    return {
        "schema_version": 1,
        "mode": "config_bound_forward_profit_lock_challenger_v1",
        "contract": _contract(),
        "summary": _summary(attempts),
        "latest_results": results,
        "limitations": _limitations(),
    }


def _lifecycle(
    candles: Mapping[int, CandleLike], attempt: Record, fee_rate: float
) -> dict[str, object]:
    side = text(attempt.get("side"), "attempt side")
    entry_time = nonnegative_int(attempt.get("entry_time_ms"), "entry time")
    current_time = nonnegative_int(
        attempt.get("current_exit_time_ms"), "current exit time"
    )
    entry_price = _positive(attempt.get("entry_price"), "entry price")
    size = _positive(attempt.get("position_quantity"), "position quantity")
    notional = _positive(attempt.get("entry_notional_usd"), "entry notional")
    current_price = _positive(attempt.get("current_exit_price"), "current exit price")
    _reconcile_notional(entry_price, size, notional)
    challenge = build_open_profit_lock_challenger(
        candles,
        side,
        {"venue_timestamp_ms": entry_time, "price": entry_price, "size": size},
        _marked_economics(attempt, fee_rate, entry_price, size, current_price),
        current_time,
    )
    return {
        **_identity(attempt),
        "status": text(attempt.get("status"), "attempt status"),
        "entry_time_ms": entry_time,
        "as_of_timestamp_ms": current_time,
        "current_exact_net_excluding_funding_bps": _current_net(attempt),
        "completed_bars_expected": challenge["completed_bars_expected"],
        "completed_bars_observed": challenge["completed_bars_observed"],
        "policies": challenge["policies"],
    }


def _marked_economics(
    attempt: Record,
    fee_rate: float,
    entry_price: float,
    size: float,
    current_price: float,
) -> dict[str, float]:
    direction = 1.0 if text(attempt.get("side"), "attempt side") == "long" else -1.0
    entry_fee = entry_price * size * fee_rate
    funding = (
        number(attempt.get("current_funding_bps"), "current funding bps")
        * entry_price
        * size
        / _BPS
    )
    gross = direction * (current_price - entry_price) * size
    return {
        "mark_price": current_price,
        "fees_usd": entry_fee,
        "funding_usd": funding,
        "active_lifecycle_marked_net_pnl_usd": gross - entry_fee + funding,
    }


def _identity(attempt: Record) -> dict[str, str]:
    keys = ("candidate_strategy_id", "source_run_id", "strategy_id", "symbol", "side")
    return {key: text(attempt.get(key), key.replace("_", " ")) for key in keys}


def _current_net(attempt: Record) -> float:
    gross = number(attempt.get("current_gross_return_bps"), "current gross return")
    fee = number(attempt.get("current_fee_bps"), "current fee")
    funding = number(attempt.get("current_funding_bps"), "current funding")
    reported = number(attempt.get("current_net_return_bps"), "current net return")
    if not math.isclose(
        reported, gross - fee + funding, abs_tol=_RECONCILIATION_TOLERANCE
    ):
        raise ValueError("exact current return components do not reconcile")
    return gross - fee


def _summary(attempts: list[Record]) -> dict[str, int]:
    pending = sum(row.get("status") == "exit_pending" for row in attempts)
    return {
        "lifecycles": len(attempts),
        "pending": pending,
        "resolved": len(attempts) - pending,
    }


def _fee_rate(value: float) -> float:
    rate = number(value, "taker fee rate")
    if rate <= 0.0 or rate >= 1.0:
        raise ValueError("taker fee rate must be within (0, 1)")
    return rate


def _positive(value: object, label: str) -> float:
    parsed = number(value, label)
    if parsed <= 0.0:
        raise ValueError(f"{label} must be positive")
    return parsed


def _reconcile_notional(price: float, size: float, notional: float) -> None:
    if not math.isclose(price * size, notional, abs_tol=_RECONCILIATION_TOLERANCE):
        raise ValueError("entry price, size, and notional do not reconcile")


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_promotion": False,
        "native_exit_policy_changed": False,
    }


def _limitations() -> list[str]:
    return [
        "the native configured exit remains authoritative and unchanged",
        "profit-lock policies were predeclared for earlier HYPE research, not fitted to SOL",
        "activation and triggering use causal completed one-minute candles",
        "counterfactual exits use trigger reference prices and taker fees without extra slippage",
        "counterfactual policy economics exclude funding accrued before an earlier trigger",
        "recorded visible depth is not proof of a live IOC fill",
        "the challenger cannot route, close, resize, promote, or submit a trade",
    ]
