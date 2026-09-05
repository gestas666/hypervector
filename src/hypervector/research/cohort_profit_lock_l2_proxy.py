"""Causal L2-midpoint proxy evidence for frozen profit-lock policies."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Literal

from hypervector.research.cohort_profit_lock_policy import (
    POLICIES,
    ProfitLockPolicy,
    evaluate_profit_lock_path,
    policy_declaration,
)

_MINUTE_MS = 60_000


@dataclass(frozen=True)
class ProxyLifecycle:
    """One historical lifecycle with reconciled fee and PnL inputs."""

    lifecycle_id: str
    phase: str
    side: str
    entry_timestamp_ms: int
    exit_timestamp_ms: int
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl_usd: float
    fees_usd: float


@dataclass(frozen=True)
class ProxyMinuteBar:
    """One completed L2-midpoint minute and its continuity evidence."""

    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    snapshot_count: int
    first_delay_ms: int
    maximum_internal_gap_ms: int
    end_boundary_age_ms: int


def build_profit_lock_proxy_report(
    lifecycles: Sequence[ProxyLifecycle],
    bars: Mapping[int, ProxyMinuteBar],
    completeness_thresholds_ms: Sequence[int],
    *,
    path_source: Literal["l2_midpoint_proxy", "exact_exchange_mark"] = (
        "l2_midpoint_proxy"
    ),
) -> dict[str, object]:
    """Build report-only causal profit-lock proxy evidence."""
    thresholds = _validate_inputs(lifecycles, bars, completeness_thresholds_ms)
    mode, limitations = _source_contract(path_source)
    return {
        "schema_version": 1,
        "mode": mode,
        "path_source": path_source,
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
            "automatic_promotion": False,
        },
        "limitations": limitations,
        "thresholds_ms": {
            str(threshold): _threshold_report(lifecycles, bars, threshold)
            for threshold in thresholds
        },
    }


def _source_contract(
    path_source: Literal["l2_midpoint_proxy", "exact_exchange_mark"],
) -> tuple[str, list[str]]:
    common = [
        "counterfactual economics exclude funding and additional exit slippage",
        "a trigger after the first incomplete minute is withheld",
        "policy parameters were predeclared and are not fitted by this report",
    ]
    if path_source == "exact_exchange_mark":
        return (
            "cohort_profit_lock_exact_exchange_mark_v1",
            [
                "sampled exchange mark OHLC cannot reconstruct intrainterval mark movement",
                *common,
            ],
        )
    if path_source == "l2_midpoint_proxy":
        return (
            "cohort_profit_lock_l2_midpoint_proxy_v1",
            [
                "L2 midpoint OHLC is a proxy rather than venue trade or mark OHLC",
                *common,
            ],
        )
    raise ValueError("profit-lock path source is unsupported")


def _threshold_report(
    lifecycles: Sequence[ProxyLifecycle],
    bars: Mapping[int, ProxyMinuteBar],
    threshold_ms: int,
) -> dict[str, object]:
    rows = [_lifecycle_result(value, bars, threshold_ms) for value in lifecycles]
    phases = sorted({value.phase for value in lifecycles})
    sides = sorted({value.side for value in lifecycles})
    return {
        "lifecycles": rows,
        "overall": _phase_summary(rows),
        "by_phase": {
            phase: _phase_summary([row for row in rows if row["phase"] == phase])
            for phase in phases
        },
        "by_side": {
            side: _phase_summary([row for row in rows if row["side"] == side])
            for side in sides
        },
    }


def _lifecycle_result(
    lifecycle: ProxyLifecycle,
    bars: Mapping[int, ProxyMinuteBar],
    threshold_ms: int,
) -> dict[str, object]:
    prefix, first_bad = _complete_prefix(lifecycle, bars, threshold_ms)
    policies = {
        policy.policy_id: _policy_result(policy, lifecycle, prefix, first_bad)
        for policy in POLICIES
    }
    resolved = sum(bool(value["resolved"]) for value in policies.values())
    return {
        "lifecycle_id": lifecycle.lifecycle_id,
        "phase": lifecycle.phase,
        "side": lifecycle.side,
        "status": _lifecycle_status(resolved, first_bad),
        "first_incomplete_minute_ms": first_bad,
        "policies": policies,
    }


def _complete_prefix(
    lifecycle: ProxyLifecycle,
    bars: Mapping[int, ProxyMinuteBar],
    threshold_ms: int,
) -> tuple[tuple[ProxyMinuteBar, ...], int | None]:
    first = ((lifecycle.entry_timestamp_ms + _MINUTE_MS - 1) // _MINUTE_MS) * _MINUTE_MS
    last = ((lifecycle.exit_timestamp_ms - _MINUTE_MS) // _MINUTE_MS) * _MINUTE_MS
    prefix: list[ProxyMinuteBar] = []
    for timestamp_ms in range(first, last + _MINUTE_MS, _MINUTE_MS):
        bar = bars.get(timestamp_ms)
        if bar is None or not _bar_complete(bar, threshold_ms):
            return tuple(prefix), timestamp_ms
        prefix.append(bar)
    return tuple(prefix), None


def _policy_result(
    policy: ProfitLockPolicy,
    lifecycle: ProxyLifecycle,
    prefix: Sequence[ProxyMinuteBar],
    first_bad: int | None,
) -> dict[str, object]:
    state = evaluate_profit_lock_path(
        policy, lifecycle.side, prefix, lifecycle.entry_price
    )
    actual = lifecycle.gross_pnl_usd - lifecycle.fees_usd
    if state.trigger is not None:
        estimated = _trigger_net(lifecycle, state.trigger.reference_price)
        return _policy_payload(policy, True, estimated, actual, state.trigger)
    if first_bad is None:
        return _policy_payload(policy, False, actual, actual, None)
    return {
        **policy_declaration(policy),
        "resolved": False,
        "triggered": False,
        "estimated_net_ex_funding_usd": None,
        "actual_net_ex_funding_usd": actual,
        "trigger_timestamp_ms": None,
        "reference_price": None,
    }


def _policy_payload(
    policy: ProfitLockPolicy,
    triggered: bool,
    estimated: float,
    actual: float,
    trigger: object | None,
) -> dict[str, object]:
    timestamp = getattr(trigger, "trigger_timestamp_ms", None)
    reference = getattr(trigger, "reference_price", None)
    return {
        **policy_declaration(policy),
        "resolved": True,
        "triggered": triggered,
        "estimated_net_ex_funding_usd": estimated,
        "actual_net_ex_funding_usd": actual,
        "trigger_timestamp_ms": timestamp,
        "reference_price": reference,
    }


def _phase_summary(rows: Sequence[dict[str, object]]) -> dict[str, object]:
    return {
        policy.policy_id: _policy_summary(
            [row["policies"][policy.policy_id] for row in rows]  # type: ignore[index]
        )
        for policy in POLICIES
    }


def _policy_summary(rows: Sequence[object]) -> dict[str, object]:
    values = [row for row in rows if isinstance(row, Mapping)]
    resolved = [row for row in values if row["resolved"] is True]
    estimated = [float(row["estimated_net_ex_funding_usd"]) for row in resolved]
    actual = [float(row["actual_net_ex_funding_usd"]) for row in resolved]
    gross_profit = sum(value for value in estimated if value > 0.0)
    gross_loss = -sum(value for value in estimated if value < 0.0)
    return {
        "trades": len(values),
        "resolved": len(resolved),
        "withheld": len(values) - len(resolved),
        "triggered": sum(row["triggered"] is True for row in resolved),
        "wins": sum(value > 0.0 for value in estimated),
        "losses": sum(value < 0.0 for value in estimated),
        "breakeven": sum(value == 0.0 for value in estimated),
        "estimated_net_ex_funding_usd": _rounded(sum(estimated)),
        "actual_net_ex_funding_same_rows_usd": _rounded(sum(actual)),
        "delta_usd": _rounded(sum(estimated) - sum(actual)),
        "profit_factor": None
        if gross_loss == 0.0
        else _rounded(gross_profit / gross_loss),
        "net_excluding_largest_winner_usd": _without_largest(estimated),
    }


def _trigger_net(lifecycle: ProxyLifecycle, reference_price: float) -> float:
    denominator = lifecycle.quantity * (lifecycle.entry_price + lifecycle.exit_price)
    fee_rate = lifecycle.fees_usd / denominator
    direction = 1.0 if lifecycle.side == "long" else -1.0
    gross = direction * (reference_price - lifecycle.entry_price) * lifecycle.quantity
    fees = fee_rate * lifecycle.quantity * (lifecycle.entry_price + reference_price)
    return gross - fees


def _validate_inputs(
    lifecycles: Sequence[ProxyLifecycle],
    bars: Mapping[int, ProxyMinuteBar],
    thresholds: Sequence[int],
) -> tuple[int, ...]:
    values = tuple(thresholds)
    if not lifecycles or not values or values != tuple(sorted(set(values))):
        raise ValueError(
            "profit-lock proxy requires lifecycles and ordered unique thresholds"
        )
    if any(isinstance(value, bool) or value <= 0 for value in values):
        raise ValueError("profit-lock proxy thresholds must be positive integers")
    for lifecycle in lifecycles:
        _validate_lifecycle(lifecycle)
    for timestamp_ms, bar in bars.items():
        if timestamp_ms != bar.timestamp_ms or timestamp_ms % _MINUTE_MS:
            raise ValueError("profit-lock proxy bar identity is invalid")
    return values


def _validate_lifecycle(value: ProxyLifecycle) -> None:
    numeric = (
        value.entry_price,
        value.exit_price,
        value.quantity,
        value.gross_pnl_usd,
        value.fees_usd,
    )
    valid = (
        bool(value.lifecycle_id)
        and bool(value.phase)
        and value.side in {"long", "short"}
        and 0 <= value.entry_timestamp_ms < value.exit_timestamp_ms
        and all(math.isfinite(item) for item in numeric)
        and min(value.entry_price, value.exit_price, value.quantity) > 0.0
        and value.fees_usd >= 0.0
    )
    if not valid:
        raise ValueError("profit-lock proxy lifecycle is invalid")


def _bar_complete(bar: ProxyMinuteBar, threshold_ms: int) -> bool:
    return (
        bar.snapshot_count >= 2
        and max(
            bar.first_delay_ms,
            bar.maximum_internal_gap_ms,
            bar.end_boundary_age_ms,
        )
        <= threshold_ms
    )


def _lifecycle_status(resolved: int, first_bad: int | None) -> str:
    if resolved == len(POLICIES):
        return "resolved_complete_path" if first_bad is None else "resolved_before_gap"
    if resolved == 0:
        return "withheld_incomplete_l2_prefix"
    return "mixed_policy_resolution_before_gap"


def _rounded(value: float) -> float:
    return round(value, 6)


def _without_largest(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return _rounded(sum(values) - max(max(values), 0.0))
