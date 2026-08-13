"""Report-only exits after favorable excursion, support decay, and retrace."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

from hypervector.research.cohort_lifecycle_evidence import (
    FillAggregate,
    build_fill_index,
    build_funding_index,
)
from hypervector.research.cohort_profit_lock_lifecycle import support_decay_gate
from hypervector.research.cohort_profit_lock_lifecycle_values import (
    Identity,
    completed_bars,
    lifecycle_economics,
    lifecycle_identity,
    lifecycle_payload,
)
from hypervector.research.cohort_profit_lock_mechanism import (
    build_normalized_support_decay_retrace_report,
)
from hypervector.research.cohort_profit_lock_results import (
    ProfitLockEconomics,
    estimate_counterfactual_net,
)
from hypervector.research.cohort_regime_opposition import (
    build_regime_support_decay_episode,
)
from hypervector.research.cohort_trade_reflection_index import (
    Candle,
    ReflectionEvidenceIndex,
    build_reflection_evidence_index,
)

Record = Mapping[str, object]
_STRATEGY_ID = "hype_breakout_onset_bidirectional_v1"
_CANONICAL_STRATEGY = "range_onset_bidirectional_v1"
_MINUTE_MS = 60_000


@dataclass(frozen=True)
class SupportDecayRetracePolicy:
    """One MFE activation and cost-adjusted net retrace threshold."""

    policy_id: str
    activation_mfe_bps: float
    exit_net_floor_bps: float


@dataclass(frozen=True)
class SupportDecayRetraceTrigger:
    """First next-open exit scheduled by a completed retrace decision."""

    activation_timestamp_ms: int
    support_decay_trigger_timestamp_ms: int
    decision_timestamp_ms: int
    exit_timestamp_ms: int
    decision_close_price: float
    decision_net_return_bps: float
    exit_reference_price: float
    best_completed_price: float


@dataclass(frozen=True)
class SupportDecayRetraceState:
    """Causal path state for one report-only retrace policy."""

    activation_timestamp_ms: int | None
    best_completed_price: float
    trigger: SupportDecayRetraceTrigger | None


POLICIES = (
    SupportDecayRetracePolicy("mfe25_decay_net5", 25.0, 5.0),
    SupportDecayRetracePolicy("mfe40_decay_net5", 40.0, 5.0),
    SupportDecayRetracePolicy("mfe60_decay_net5", 60.0, 5.0),
)


def evaluate_support_decay_retrace_path(
    policy: SupportDecayRetracePolicy,
    side: str,
    bars: Sequence[Candle],
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
    *,
    support_decay_trigger_ms: int,
) -> SupportDecayRetraceState:
    """Evaluate a next-open exit without same-bar activation or look-ahead."""
    _validate_path(policy, side, bars, economics, support_decay_trigger_ms)
    best = economics.entry_price
    activation_ms: int | None = None
    for index, candle in enumerate(bars):
        if index > 0 and _gate_precedes_decision(
            activation_ms, support_decay_trigger_ms, candle.timestamp_ms
        ):
            decision = bars[index - 1]
            decision_net_bps = _net_return_bps(
                side,
                candle.timestamp_ms,
                decision.close * economics.fill_reference_ratio,
                economics,
                funding,
            )
            if decision_net_bps <= policy.exit_net_floor_bps:
                trigger = SupportDecayRetraceTrigger(
                    activation_timestamp_ms=_required_timestamp(activation_ms),
                    support_decay_trigger_timestamp_ms=support_decay_trigger_ms,
                    decision_timestamp_ms=candle.timestamp_ms,
                    exit_timestamp_ms=candle.timestamp_ms,
                    decision_close_price=decision.close,
                    decision_net_return_bps=decision_net_bps,
                    exit_reference_price=candle.open,
                    best_completed_price=best,
                )
                return SupportDecayRetraceState(activation_ms, best, trigger)
        best = _best_price(side, best, candle)
        if (
            activation_ms is None
            and _directional_bps(side, economics.entry_price, best)
            >= policy.activation_mfe_bps
        ):
            activation_ms = candle.timestamp_ms
    return SupportDecayRetraceState(activation_ms, best, None)


def build_support_decay_retrace_mechanism(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    reflected_trades: Sequence[Record],
) -> dict[str, object]:
    """Build exact-provider normalized evidence for the frozen retrace policies."""
    scoped = [
        trade for trade in reflected_trades if trade.get("strategy_id") == _STRATEGY_ID
    ]
    evidence = build_reflection_evidence_index(cohort_records)
    fills = build_fill_index(asset_records)
    funding = build_funding_index(asset_records)
    results = [_lifecycle_result(trade, evidence, fills, funding) for trade in scoped]
    results.sort(key=lambda row: int(row["exit_timestamp_ms"]))
    report = build_normalized_support_decay_retrace_report(
        results,
        policies=[policy_declaration(policy) for policy in POLICIES],
        contract=_contract(),
        activation_contract=_activation_contract(),
        limitations=_limitations(),
    )
    report["strategy_scope"] = _STRATEGY_ID
    report["source_lifecycles"] = len(scoped)
    report["trial_accounting"] = {
        "predeclared_policy_trials": len(POLICIES),
        "selection_performed": False,
    }
    return report


def policy_declaration(policy: SupportDecayRetracePolicy) -> dict[str, object]:
    """Serialize one validated retrace policy."""
    _validate_policy(policy)
    return {
        "policy_id": policy.policy_id,
        "activation_mfe_bps": policy.activation_mfe_bps,
        "exit_net_floor_bps": policy.exit_net_floor_bps,
    }


def _lifecycle_result(
    trade: Record,
    evidence: ReflectionEvidenceIndex,
    fills: Mapping[tuple[str, int], FillAggregate],
    funding: Mapping[str, Mapping[int, float]],
) -> dict[str, object]:
    identity = lifecycle_identity(trade)
    symbol_funding = funding.get(identity[1], {})
    economics = lifecycle_economics(trade, fills, symbol_funding)
    episode = build_regime_support_decay_episode(
        identity[3],
        evidence.timelines.get((identity[2], identity[1]), ()),
        evidence.timelines.get((_CANONICAL_STRATEGY, identity[1]), ()),
        entry_timestamp_ms=economics.entry_timestamp_ms,
        end_timestamp_ms=economics.exit_timestamp_ms,
    )
    available, gate_ms = support_decay_gate(episode, economics)
    if not available:
        return _unavailable_result(
            identity, economics, "missing_support_decay_evidence"
        )
    if gate_ms is None:
        return _unchanged_result(identity, economics, "no_persistent_support_decay")
    expected, observed = completed_bars(
        evidence.candles.get(identity[1], {}),
        economics.entry_timestamp_ms,
        economics.exit_timestamp_ms,
    )
    if len(expected) != len(observed):
        return _unavailable_result(
            identity,
            economics,
            "incomplete_candle_coverage",
            expected=len(expected),
            observed=len(observed),
        )
    policies = {
        policy.policy_id: _policy_result(
            policy,
            identity[3],
            observed,
            economics,
            symbol_funding,
            gate_ms,
        )
        for policy in POLICIES
    }
    return lifecycle_payload(
        identity,
        economics,
        "eligible_persistent_support_decay",
        policies,
        expected=len(expected),
        observed=len(observed),
    )


def _policy_result(
    policy: SupportDecayRetracePolicy,
    side: str,
    bars: Sequence[Candle],
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
    gate_ms: int,
) -> dict[str, object]:
    state = evaluate_support_decay_retrace_path(
        policy,
        side,
        bars,
        economics,
        funding,
        support_decay_trigger_ms=gate_ms,
    )
    base = {
        **policy_declaration(policy),
        "support_decay_trigger_timestamp_ms": gate_ms,
        "activation_timestamp_ms": state.activation_timestamp_ms,
        "actual_net_pnl_usd": economics.actual_net_pnl_usd,
    }
    if state.trigger is None:
        return {
            **base,
            "status": "not_triggered_before_actual_exit",
            "trigger_timestamp_ms": None,
            "estimated_exit_price": economics.actual_exit_price,
            "estimated_net_pnl_usd": economics.actual_net_pnl_usd,
            "estimated_minus_actual_net_usd": 0.0,
        }
    trigger = state.trigger
    estimated_exit = trigger.exit_reference_price * economics.fill_reference_ratio
    estimated_net = estimate_counterfactual_net(
        side,
        trigger.exit_timestamp_ms,
        estimated_exit,
        economics,
        funding,
    )
    return {
        **base,
        "status": "triggered",
        "trigger_timestamp_ms": trigger.exit_timestamp_ms,
        "decision_close_price": trigger.decision_close_price,
        "decision_net_return_bps": trigger.decision_net_return_bps,
        "exit_reference_price": trigger.exit_reference_price,
        "best_completed_price_before_trigger": trigger.best_completed_price,
        "estimated_exit_price": estimated_exit,
        "estimated_net_pnl_usd": estimated_net,
        "estimated_minus_actual_net_usd": estimated_net - economics.actual_net_pnl_usd,
    }


def _unavailable_result(
    identity: Identity,
    economics: ProfitLockEconomics,
    reason: str,
    *,
    expected: int | None = None,
    observed: int | None = None,
) -> dict[str, object]:
    policies = {
        policy.policy_id: {
            **policy_declaration(policy),
            "status": f"withheld_{reason}",
            "estimated_net_pnl_usd": None,
            "actual_net_pnl_usd": economics.actual_net_pnl_usd,
        }
        for policy in POLICIES
    }
    return lifecycle_payload(
        identity,
        economics,
        reason,
        policies,
        expected=expected,
        observed=observed,
    )


def _unchanged_result(
    identity: Identity,
    economics: ProfitLockEconomics,
    reason: str,
) -> dict[str, object]:
    policies = {
        policy.policy_id: {
            **policy_declaration(policy),
            "status": "not_activated_no_persistent_support_decay",
            "estimated_net_pnl_usd": economics.actual_net_pnl_usd,
            "actual_net_pnl_usd": economics.actual_net_pnl_usd,
        }
        for policy in POLICIES
    }
    return lifecycle_payload(identity, economics, reason, policies)


def _validate_path(
    policy: SupportDecayRetracePolicy,
    side: str,
    bars: Sequence[Candle],
    economics: ProfitLockEconomics,
    support_decay_trigger_ms: int,
) -> None:
    _validate_policy(policy)
    if side not in {"long", "short"}:
        raise ValueError("support-decay retrace side must be long or short")
    if support_decay_trigger_ms % _MINUTE_MS:
        raise ValueError("support-decay retrace gate must align to a minute")
    if support_decay_trigger_ms <= economics.entry_timestamp_ms:
        raise ValueError("support-decay retrace gate must follow entry")
    timestamps = [bar.timestamp_ms for bar in bars]
    if timestamps != sorted(set(timestamps)):
        raise ValueError("support-decay retrace bars must be strictly chronological")


def _validate_policy(policy: SupportDecayRetracePolicy) -> None:
    values = (policy.activation_mfe_bps, policy.exit_net_floor_bps)
    if not policy.policy_id.strip() or any(
        not math.isfinite(value) or value < 0.0 for value in values
    ):
        raise ValueError("support-decay retrace policy is invalid")
    if policy.activation_mfe_bps <= policy.exit_net_floor_bps:
        raise ValueError("support-decay retrace activation must exceed its net floor")


def _gate_precedes_decision(
    activation_ms: int | None,
    support_decay_ms: int,
    decision_ms: int,
) -> bool:
    return (
        activation_ms is not None
        and activation_ms < decision_ms
        and support_decay_ms < decision_ms
    )


def _best_price(side: str, best: float, candle: Candle) -> float:
    return max(best, candle.high) if side == "long" else min(best, candle.low)


def _directional_bps(side: str, entry: float, price: float) -> float:
    direction = 1.0 if side == "long" else -1.0
    return direction * (price / entry - 1.0) * 10_000.0


def _net_return_bps(
    side: str,
    timestamp_ms: int,
    exit_price: float,
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
) -> float:
    net = estimate_counterfactual_net(
        side, timestamp_ms, exit_price, economics, funding
    )
    return net / (economics.entry_price * economics.size) * 10_000.0


def _required_timestamp(value: int | None) -> int:
    if value is None:
        raise RuntimeError("validated support-decay retrace activation is absent")
    return value


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "balance_gate": False,
        "portfolio_pnl_claimed": False,
    }


def _activation_contract() -> dict[str, object]:
    return {
        "source": "causal_regime_support_decay_persistence_v1",
        "persistence_decisions": 5,
        "support_decay_threshold": 0.25,
        "exit_timing": "next_open_after_completed_bar_retrace",
        "same_bar_activation_and_trigger_allowed": False,
        "same_bar_support_decay_and_trigger_allowed": False,
        "cost_basis": "measured_entry_fee_plus_observed_exit_fill_ratio_and_fee_rate",
    }


def _limitations() -> list[str]:
    return [
        "the hypothesis was specified after observing live favorable-excursion giveback",
        "completed one-minute bars cannot reconstruct private queue state",
        "counterfactual exits reuse each actual exit fill/reference ratio and fee rate",
        "mixed source profiles remain normalized mechanism evidence, not portfolio PnL",
        "small exact-provider samples cannot establish a durable exit edge",
        "this report cannot gate, size, route, close, or submit a trade",
    ]
