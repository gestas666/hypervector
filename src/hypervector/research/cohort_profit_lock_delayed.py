"""Report-only completed-minute lock replay with delayed execution proxies."""

from collections.abc import Mapping, Sequence
import math

from hypervector.cohort_profit_lock_policy import (
    CandleLike,
    ProfitLockPolicy,
    ProfitLockTrigger,
    evaluate_profit_lock_path,
)
from hypervector.research.cohort_profit_lock_results import (
    ProfitLockEconomics,
    estimate_counterfactual_net,
    unchanged_policy,
    withheld_policy,
)

_MINUTE_MS = 60_000
_BPS = 10_000.0


def build_delayed_profit_lock_result(
    policy: ProfitLockPolicy,
    side: str,
    bars: Sequence[CandleLike],
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
    *,
    adverse_bps: float,
) -> dict[str, object]:
    """Value a causal lock at trigger close with explicit adverse execution stress.

    This is a proxy, not an executable quote or a promise of a stop-price fill.
    Exclude the entry minute exactly as the live controller does. Missing required
    minutes withhold the result, including paths with a trigger before a later gap.
    """
    if not math.isfinite(adverse_bps) or not 0 <= adverse_bps < _BPS:
        raise ValueError("adverse_bps must be finite and in [0, 10000)")
    first = economics.entry_timestamp_ms // _MINUTE_MS * _MINUTE_MS + _MINUTE_MS
    last = (economics.exit_timestamp_ms - _MINUTE_MS) // _MINUTE_MS * _MINUTE_MS
    scoped = tuple(bar for bar in bars if first <= bar.timestamp_ms <= last)
    if tuple(bar.timestamp_ms for bar in scoped) != tuple(
        range(first, last + 1, _MINUTE_MS)
    ):
        return withheld_policy(policy, economics)
    state = evaluate_profit_lock_path(policy, side, scoped, economics.entry_price)
    status = (
        "not_activated_before_actual_exit"
        if state.activation_timestamp_ms is None
        else "armed_not_triggered_before_actual_exit"
    )
    result = unchanged_policy(policy, economics, status, state.activation_timestamp_ms)
    trigger = state.trigger
    if trigger is not None:
        bar = next(
            bar for bar in scoped if bar.timestamp_ms == trigger.trigger_timestamp_ms
        )
        result.update(
            _triggered_values(side, trigger, bar.close, economics, funding, adverse_bps)
        )
    result["fill_model"] = "completed_trigger_close_adverse_bps_proxy"
    result["adverse_bps"] = adverse_bps
    return result


def _triggered_values(
    side: str,
    trigger: ProfitLockTrigger,
    close: float,
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
    adverse_bps: float,
) -> dict[str, object]:
    direction = 1 if side == "long" else -1
    price = close * (1 - direction * adverse_bps / _BPS)
    decision_ms = trigger.trigger_timestamp_ms + _MINUTE_MS
    net = estimate_counterfactual_net(side, decision_ms, price, economics, funding)
    return {
        "status": "triggered",
        "trigger_timestamp_ms": trigger.trigger_timestamp_ms,
        "decision_time_ms": decision_ms,
        "stop_price_before_trigger": trigger.stop_price,
        "estimated_exit_price": price,
        "estimated_net_pnl_usd": net,
        "estimated_minus_actual_net_usd": net - economics.actual_net_pnl_usd,
    }
