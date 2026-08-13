"""Report-only profit-lock state for one currently open lifecycle."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

from hypervector.research.cohort_live_audit_values import (
    nonnegative_int,
    number,
    text,
)
from hypervector.research.cohort_profit_lock_policy import (
    CandleLike,
    POLICIES,
    ProfitLockPathState,
    ProfitLockPolicy,
    evaluate_profit_lock_path,
    policy_declaration,
)

Record = Mapping[str, object]
_MINUTE_MS = 60_000
_COMPLETED_BAR_ARRIVAL_GRACE_MS = 60_000
_MONEY_TOLERANCE = 0.000_005


@dataclass(frozen=True)
class _OpenEconomics:
    direction: float
    entry_price: float
    size: float
    mark_price: float
    entry_fee: float
    fee_rate: float


def build_open_profit_lock_challenger(
    candles: Mapping[int, CandleLike],
    side: str,
    entry: Record,
    marked_economics: Record,
    as_of_ms: int,
    *,
    policies: Sequence[ProfitLockPolicy] = POLICIES,
) -> dict[str, object]:
    """Evaluate predeclared locks on a causal completed-candle prefix."""
    direction = text(side, "open profit-lock side")
    entry_ms = nonnegative_int(entry.get("venue_timestamp_ms"), "entry timestamp")
    entry_price = number(entry.get("price"), "entry price")
    observed_ms = nonnegative_int(as_of_ms, "open profit-lock as-of")
    if direction not in {"long", "short"} or entry_price <= 0.0:
        raise ValueError("open profit-lock entry or side is invalid")
    if observed_ms < entry_ms:
        raise ValueError("open profit-lock as-of precedes entry")
    economics = _open_economics(direction, entry, marked_economics)
    expected, observed = _completed_bars(candles, entry_ms, observed_ms)
    complete = len(expected) == len(observed)
    policies = {
        policy.policy_id: _with_counterfactual_economics(
            _policy_result(policy, direction, observed, entry_price, complete),
            economics,
        )
        for policy in policies
    }
    status = _status(expected, complete)
    return {
        "schema_version": 2,
        "mode": "cohort_open_profit_lock_challenger_v2",
        "contract": _contract(),
        "policy_origin": "existing_predeclared_hype_profit_research_v1",
        "status": status,
        "entry_timestamp_ms": entry_ms,
        "as_of_timestamp_ms": observed_ms,
        "completed_bar_arrival_grace_ms": _COMPLETED_BAR_ARRIVAL_GRACE_MS,
        "completed_bars_expected": len(expected),
        "completed_bars_observed": len(observed),
        "policies": policies,
        "limitations": _limitations(),
    }


def _completed_bars(
    candles: Mapping[int, CandleLike],
    entry_ms: int,
    as_of_ms: int,
) -> tuple[tuple[int, ...], tuple[CandleLike, ...]]:
    first = ((entry_ms + _MINUTE_MS - 1) // _MINUTE_MS) * _MINUTE_MS
    eligible_close_ms = as_of_ms - _COMPLETED_BAR_ARRIVAL_GRACE_MS
    if eligible_close_ms < _MINUTE_MS:
        return (), ()
    last = ((eligible_close_ms - _MINUTE_MS) // _MINUTE_MS) * _MINUTE_MS
    expected = (
        () if last < first else tuple(range(first, last + _MINUTE_MS, _MINUTE_MS))
    )
    observed: list[CandleLike] = []
    for timestamp_ms in expected:
        candle = candles.get(timestamp_ms)
        if candle is not None:
            if candle.timestamp_ms != timestamp_ms:
                raise ValueError("open profit-lock candle key and timestamp disagree")
            observed.append(candle)
    return expected, tuple(observed)


def _policy_result(
    policy: ProfitLockPolicy,
    side: str,
    bars: tuple[CandleLike, ...],
    entry_price: float,
    complete: bool,
) -> dict[str, object]:
    if not complete:
        return _withheld_policy(policy)
    state = evaluate_profit_lock_path(policy, side, bars, entry_price)
    if state.trigger is not None:
        return _triggered_policy(policy, state)
    if state.activation_timestamp_ms is not None:
        return _armed_policy(policy, state)
    return _inactive_policy(policy, state)


def _triggered_policy(
    policy: ProfitLockPolicy,
    state: ProfitLockPathState,
) -> dict[str, object]:
    trigger = state.trigger
    if trigger is None:
        raise ValueError("triggered profit-lock policy lacks a trigger")
    return {
        **policy_declaration(policy),
        "status": "triggered_before_current_boundary",
        "activation_timestamp_ms": trigger.activation_timestamp_ms,
        "trigger_timestamp_ms": trigger.trigger_timestamp_ms,
        "trigger_reference_price": trigger.reference_price,
        "stop_price_before_trigger": trigger.stop_price,
        "best_completed_price_before_trigger": trigger.best_completed_price,
        "best_completed_price": None,
        "active_stop_price": None,
    }


def _armed_policy(
    policy: ProfitLockPolicy,
    state: ProfitLockPathState,
) -> dict[str, object]:
    return {
        **policy_declaration(policy),
        "status": "armed_not_triggered",
        "activation_timestamp_ms": state.activation_timestamp_ms,
        "trigger_timestamp_ms": None,
        "trigger_reference_price": None,
        "stop_price_before_trigger": None,
        "best_completed_price_before_trigger": None,
        "best_completed_price": state.best_completed_price,
        "active_stop_price": state.active_stop_price,
    }


def _inactive_policy(
    policy: ProfitLockPolicy,
    state: ProfitLockPathState,
) -> dict[str, object]:
    payload = _armed_policy(policy, state)
    payload["status"] = "not_activated"
    return payload


def _withheld_policy(policy: ProfitLockPolicy) -> dict[str, object]:
    payload = _inactive_policy(
        policy,
        ProfitLockPathState(None, None, 0.0, None),
    )
    payload.update(
        {
            "status": "withheld_incomplete_candle_coverage",
            "best_completed_price": None,
        }
    )
    return payload


def _with_counterfactual_economics(
    policy: dict[str, object], economics: _OpenEconomics
) -> dict[str, object]:
    status = policy.get("status")
    if status == "triggered_before_current_boundary":
        reference = number(policy.get("trigger_reference_price"), "trigger price")
        estimate_status = "estimated_trigger_exit"
    elif status == "armed_not_triggered":
        reference = number(policy.get("active_stop_price"), "active stop price")
        estimate_status = "estimated_active_stop_exit"
    else:
        policy["counterfactual_economics"] = {
            "status": "unavailable",
            "reason": f"policy_state_{status}",
        }
        return policy
    policy["counterfactual_economics"] = _exit_estimate(
        economics, reference, estimate_status
    )
    return policy


def _exit_estimate(
    economics: _OpenEconomics, reference: float, status: str
) -> dict[str, object]:
    gross = economics.direction * (reference - economics.entry_price) * economics.size
    exit_fee = reference * economics.size * economics.fee_rate
    net = gross - economics.entry_fee - exit_fee
    current_gross = (
        economics.direction
        * (economics.mark_price - economics.entry_price)
        * economics.size
    )
    current_exit_fee = economics.mark_price * economics.size * economics.fee_rate
    current_net = current_gross - economics.entry_fee - current_exit_fee
    return {
        "status": status,
        "reference_price": reference,
        "gross_return_bps": economics.direction
        * (reference / economics.entry_price - 1.0)
        * 10_000.0,
        "gross_pnl_usd": gross,
        "estimated_entry_fee_usd": economics.entry_fee,
        "estimated_exit_fee_usd": exit_fee,
        "estimated_net_pnl_excluding_funding_usd": net,
        "estimated_current_exit_net_excluding_funding_usd": current_net,
        "estimated_minus_current_exit_net_excluding_funding_usd": net - current_net,
        "funding_included": False,
        "additional_slippage_included": False,
        "method": "measured_entry_fee_rate_causal_reference_price",
    }


def _open_economics(
    side: str, entry: Record, marked_economics: Record
) -> _OpenEconomics:
    direction = 1.0 if side == "long" else -1.0
    entry_price = _positive(entry.get("price"), "entry price")
    size = _positive(entry.get("size"), "entry size")
    mark = _positive(marked_economics.get("mark_price"), "mark price")
    entry_fee = _nonnegative(marked_economics.get("fees_usd"), "entry fee")
    funding = number(marked_economics.get("funding_usd"), "funding")
    marked_net = number(
        marked_economics.get("active_lifecycle_marked_net_pnl_usd"), "marked net"
    )
    gross = direction * (mark - entry_price) * size
    if not math.isclose(
        marked_net, gross - entry_fee + funding, abs_tol=_MONEY_TOLERANCE
    ):
        raise ValueError("open profit-lock marked economics do not reconcile")
    return _OpenEconomics(
        direction, entry_price, size, mark, entry_fee, entry_fee / (entry_price * size)
    )


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


def _status(expected: tuple[int, ...], complete: bool) -> str:
    if not complete:
        return "insufficient_candle_coverage"
    return "observed" if expected else "awaiting_completed_bar"


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "automatic_promotion": False,
    }


def _limitations() -> list[str]:
    return [
        "activation and stop updates use prior completed one-minute bars",
        "activation bars cannot trigger a newly created stop",
        "gap-through triggers use the adverse bar open",
        "missing holding candles withhold every policy",
        "counterfactual economics exclude funding and additional exit slippage",
        "policy parameters originated in HYPE research and are not fitted per market",
        "current policy states cannot close, route, size, or submit a trade",
        "open observations do not establish an exit edge",
    ]
