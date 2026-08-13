"""Per-policy economics for closed-lifecycle profit-lock challengers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.research.cohort_lifecycle_evidence import funding_sum
from hypervector.research.cohort_profit_lock_policy import (
    CandleLike,
    ProfitLockPolicy,
    ProfitLockTrigger,
    evaluate_profit_lock_path,
    policy_declaration,
)


@dataclass(frozen=True)
class ProfitLockEconomics:
    """Reconciled actual lifecycle values required by a counterfactual lock."""

    entry_timestamp_ms: int
    exit_timestamp_ms: int
    entry_price: float
    actual_exit_price: float
    size: float
    entry_fee_usd: float
    exit_fee_rate: float
    fill_reference_ratio: float
    actual_funding_usd: float
    actual_net_pnl_usd: float


def build_policy_result(
    policy: ProfitLockPolicy,
    side: str,
    bars: Sequence[CandleLike],
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
) -> dict[str, object]:
    """Build one unconditioned closed-lifecycle policy result."""
    state = evaluate_profit_lock_path(policy, side, bars, economics.entry_price)
    if state.trigger is None:
        status = (
            "not_activated_before_actual_exit"
            if state.activation_timestamp_ms is None
            else "armed_not_triggered_before_actual_exit"
        )
        return unchanged_policy(
            policy, economics, status, state.activation_timestamp_ms
        )
    return _triggered_result(policy, side, state.trigger, economics, funding)


def build_conditioned_policy_result(
    policy: ProfitLockPolicy,
    side: str,
    bars: Sequence[CandleLike],
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
    opposition_trigger_ms: int,
) -> dict[str, object]:
    """Build one result whose activation waits for causal regime opposition."""
    return _build_gated_policy_result(
        policy,
        side,
        bars,
        economics,
        funding,
        opposition_trigger_ms,
        gate_field="opposition_trigger_timestamp_ms",
        inactive_status="persistent_opposition_without_profit_activation",
        armed_status="persistent_opposition_armed_not_triggered_before_actual_exit",
    )


def build_support_decay_policy_result(
    policy: ProfitLockPolicy,
    side: str,
    bars: Sequence[CandleLike],
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
    support_decay_trigger_ms: int,
) -> dict[str, object]:
    """Build one result whose activation waits for persistent support decay."""
    return _build_gated_policy_result(
        policy,
        side,
        bars,
        economics,
        funding,
        support_decay_trigger_ms,
        gate_field="support_decay_trigger_timestamp_ms",
        inactive_status="support_decay_without_profit_activation",
        armed_status="support_decay_armed_not_triggered_before_actual_exit",
    )


def _build_gated_policy_result(
    policy: ProfitLockPolicy,
    side: str,
    bars: Sequence[CandleLike],
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
    gate_ms: int,
    *,
    gate_field: str,
    inactive_status: str,
    armed_status: str,
) -> dict[str, object]:
    state = evaluate_profit_lock_path(
        policy,
        side,
        bars,
        economics.entry_price,
        activation_not_before_ms=gate_ms,
    )
    if state.trigger is None:
        status = (
            inactive_status if state.activation_timestamp_ms is None else armed_status
        )
        return _gated_unchanged_policy(
            policy,
            economics,
            status,
            gate_field,
            gate_ms,
            state.activation_timestamp_ms,
        )
    payload = _triggered_result(policy, side, state.trigger, economics, funding)
    payload[gate_field] = gate_ms
    return payload


def unchanged_policy(
    policy: ProfitLockPolicy,
    economics: ProfitLockEconomics,
    status: str,
    activation_ms: int | None,
) -> dict[str, object]:
    """Retain the actual exit when one policy does not trigger."""
    return {
        **policy_declaration(policy),
        "status": status,
        "activation_timestamp_ms": activation_ms,
        "trigger_timestamp_ms": None,
        "estimated_exit_price": economics.actual_exit_price,
        "estimated_net_pnl_usd": economics.actual_net_pnl_usd,
        "actual_net_pnl_usd": economics.actual_net_pnl_usd,
        "estimated_minus_actual_net_usd": 0.0,
    }


def conditioned_unchanged_policy(
    policy: ProfitLockPolicy,
    economics: ProfitLockEconomics,
    status: str,
    opposition_trigger_ms: int | None,
    activation_ms: int | None = None,
) -> dict[str, object]:
    """Retain an actual exit and its regime-opposition boundary."""
    return _gated_unchanged_policy(
        policy,
        economics,
        status,
        "opposition_trigger_timestamp_ms",
        opposition_trigger_ms,
        activation_ms,
    )


def support_decay_unchanged_policy(
    policy: ProfitLockPolicy,
    economics: ProfitLockEconomics,
    status: str,
    support_decay_trigger_ms: int | None,
    activation_ms: int | None = None,
) -> dict[str, object]:
    """Retain an actual exit and its regime-support-decay boundary."""
    return _gated_unchanged_policy(
        policy,
        economics,
        status,
        "support_decay_trigger_timestamp_ms",
        support_decay_trigger_ms,
        activation_ms,
    )


def _gated_unchanged_policy(
    policy: ProfitLockPolicy,
    economics: ProfitLockEconomics,
    status: str,
    gate_field: str,
    gate_ms: int | None,
    activation_ms: int | None,
) -> dict[str, object]:
    payload = unchanged_policy(policy, economics, status, activation_ms)
    payload[gate_field] = gate_ms
    return payload


def withheld_policy(
    policy: ProfitLockPolicy,
    economics: ProfitLockEconomics,
) -> dict[str, object]:
    """Withhold a policy whose completed-bar coverage is incomplete."""
    return {
        **policy_declaration(policy),
        "status": "withheld_incomplete_candle_coverage",
        "activation_timestamp_ms": None,
        "trigger_timestamp_ms": None,
        "estimated_exit_price": None,
        "estimated_net_pnl_usd": None,
        "actual_net_pnl_usd": economics.actual_net_pnl_usd,
        "estimated_minus_actual_net_usd": None,
    }


def conditioned_withheld_policy(
    policy: ProfitLockPolicy,
    economics: ProfitLockEconomics,
    status: str,
    opposition_trigger_ms: int | None = None,
) -> dict[str, object]:
    """Withhold a conditioned policy while preserving its causal boundary."""
    return _gated_withheld_policy(
        policy,
        economics,
        status,
        "opposition_trigger_timestamp_ms",
        opposition_trigger_ms,
    )


def support_decay_withheld_policy(
    policy: ProfitLockPolicy,
    economics: ProfitLockEconomics,
    status: str,
    support_decay_trigger_ms: int | None = None,
) -> dict[str, object]:
    """Withhold a support-decay policy while preserving its causal boundary."""
    return _gated_withheld_policy(
        policy,
        economics,
        status,
        "support_decay_trigger_timestamp_ms",
        support_decay_trigger_ms,
    )


def _gated_withheld_policy(
    policy: ProfitLockPolicy,
    economics: ProfitLockEconomics,
    status: str,
    gate_field: str,
    gate_ms: int | None,
) -> dict[str, object]:
    payload = withheld_policy(policy, economics)
    payload["status"] = status
    payload[gate_field] = gate_ms
    return payload


def _triggered_result(
    policy: ProfitLockPolicy,
    side: str,
    trigger: ProfitLockTrigger,
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
) -> dict[str, object]:
    estimated_exit = trigger.reference_price * economics.fill_reference_ratio
    estimated_net = estimate_counterfactual_net(
        side, trigger.trigger_timestamp_ms, estimated_exit, economics, funding
    )
    return {
        **policy_declaration(policy),
        "status": "triggered",
        "activation_timestamp_ms": trigger.activation_timestamp_ms,
        "trigger_timestamp_ms": trigger.trigger_timestamp_ms,
        "trigger_reference_price": trigger.reference_price,
        "stop_price_before_trigger": trigger.stop_price,
        "best_completed_price_before_trigger": trigger.best_completed_price,
        "estimated_exit_price": estimated_exit,
        "estimated_net_pnl_usd": estimated_net,
        "actual_net_pnl_usd": economics.actual_net_pnl_usd,
        "estimated_minus_actual_net_usd": (
            estimated_net - economics.actual_net_pnl_usd
        ),
    }


def estimate_counterfactual_net(
    side: str,
    timestamp_ms: int,
    exit_price: float,
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
) -> float:
    """Estimate lifecycle net PnL at one causal counterfactual exit fill."""
    direction = 1.0 if side == "long" else -1.0
    gross = direction * (exit_price - economics.entry_price) * economics.size
    exit_fee = exit_price * economics.size * economics.exit_fee_rate
    cashflow = funding_sum(funding, economics.entry_timestamp_ms, timestamp_ms)
    return gross - economics.entry_fee_usd - exit_fee + cashflow
