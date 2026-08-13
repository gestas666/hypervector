"""Lifecycle economics for the report-only regime-loss exit challenger."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_lifecycle_evidence import (
    FillAggregate,
    funding_sum,
)
from hypervector.research.cohort_live_audit_values import (
    mapping,
    nonnegative_int,
    number,
    text,
)
from hypervector.research.cohort_profit_lock_lifecycle_values import (
    lifecycle_economics,
    lifecycle_identity,
)
from hypervector.research.cohort_profit_lock_results import (
    ProfitLockEconomics,
    estimate_counterfactual_net,
)
from hypervector.research.cohort_regime_loss_exit_policy import (
    RegimeLossExitObservation,
    RegimeLossExitResult,
    evaluate_regime_loss_exit,
)

Record = Mapping[str, object]


def build_closed_loss_exit_payload(
    trade: Record,
    fills: Mapping[tuple[str, int], FillAggregate],
    funding: Mapping[int, float],
    observations: Sequence[RegimeLossExitObservation],
    *,
    evaluated_decisions: int,
    missing_price_decisions: int,
    thresholds_bps: Sequence[float],
    persistence_decisions: int,
) -> dict[str, object]:
    """Reconcile one closed lifecycle and every frozen threshold result."""
    identity = lifecycle_identity(trade)
    economics = lifecycle_economics(trade, fills, funding)
    eligible = bool(observations)
    policies = {
        regime_loss_exit_policy_id(persistence_decisions, threshold): (
            _closed_policy(
                identity[3],
                economics,
                funding,
                observations,
                threshold,
                persistence_decisions,
            )
            if eligible
            else _withheld_closed_policy(economics, threshold, persistence_decisions)
        )
        for threshold in thresholds_bps
    }
    return {
        "status": "eligible" if eligible else "withheld_no_causal_observations",
        "lifecycle_id": identity[0],
        "symbol": identity[1],
        "strategy_id": identity[2],
        "side": identity[3],
        "source_run_id": identity[4],
        "source_profile_fingerprint": identity[5],
        "actual_net_pnl_usd": economics.actual_net_pnl_usd,
        "evaluated_decisions": evaluated_decisions,
        "observed_decisions": len(observations),
        "missing_price_decisions": missing_price_decisions,
        "policies": policies,
    }


def build_open_loss_exit_payload(
    trade: Record,
    funding: Mapping[int, float],
    observations: Sequence[RegimeLossExitObservation],
    *,
    evaluated_decisions: int,
    missing_price_decisions: int,
    thresholds_bps: Sequence[float],
    persistence_decisions: int,
) -> dict[str, object]:
    """Estimate frozen-policy state for one still-open lifecycle."""
    lifecycle = text(trade.get("lifecycle_id"), "open loss-exit lifecycle")
    symbol = text(trade.get("symbol"), "open loss-exit symbol")
    strategy = text(trade.get("strategy_id"), "open loss-exit strategy")
    side = text(trade.get("side"), "open loss-exit side")
    run_id = text(trade.get("source_run_id"), "open loss-exit run")
    _validate_side(side)
    entry = mapping(trade.get("entry"), "open loss-exit entry")
    marked = mapping(trade.get("marked_economics"), "open marked economics")
    policies = {
        regime_loss_exit_policy_id(persistence_decisions, threshold): _open_policy(
            side,
            entry,
            marked,
            funding,
            observations,
            threshold,
            persistence_decisions,
        )
        for threshold in thresholds_bps
    }
    return {
        "status": "observed" if observations else "unavailable",
        "lifecycle_id": lifecycle,
        "symbol": symbol,
        "strategy_id": strategy,
        "side": side,
        "source_run_id": run_id,
        "current_marked_net_pnl_usd": number(
            marked.get("active_lifecycle_marked_net_pnl_usd"),
            "open marked net PnL",
        ),
        "evaluated_decisions": evaluated_decisions,
        "observed_decisions": len(observations),
        "missing_price_decisions": missing_price_decisions,
        "policies": policies,
    }


def regime_loss_exit_policy_id(persistence: int, threshold: float) -> str:
    """Return the stable identifier for one declared surface cell."""
    label = format(threshold, "g").replace(".", "p")
    return f"opp{persistence}_loss{label}"


def _closed_policy(
    side: str,
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
    observations: Sequence[RegimeLossExitObservation],
    threshold: float,
    persistence: int,
) -> dict[str, object]:
    result = evaluate_regime_loss_exit(
        side=side,
        entry_price=economics.entry_price,
        observations=observations,
        loss_threshold_bps=threshold,
        persistence_decisions=persistence,
    )
    if result.state != "triggered":
        return {
            **_policy_declaration(threshold, persistence),
            **_result_fields(result),
            "status": "retained_actual_exit",
            "estimated_exit_price": economics.actual_exit_price,
            "estimated_net_pnl_usd": economics.actual_net_pnl_usd,
            "actual_net_pnl_usd": economics.actual_net_pnl_usd,
            "estimated_minus_actual_net_usd": 0.0,
        }
    trigger_ms = nonnegative_int(
        result.trigger_decision_time_ms, "loss-exit trigger time"
    )
    reference = number(result.exit_reference_price, "loss-exit reference")
    estimated_exit = reference * economics.fill_reference_ratio
    estimated_net = estimate_counterfactual_net(
        side, trigger_ms, estimated_exit, economics, funding
    )
    return {
        **_policy_declaration(threshold, persistence),
        **_result_fields(result),
        "status": "triggered",
        "estimated_exit_price": estimated_exit,
        "estimated_net_pnl_usd": estimated_net,
        "actual_net_pnl_usd": economics.actual_net_pnl_usd,
        "estimated_minus_actual_net_usd": estimated_net - economics.actual_net_pnl_usd,
    }


def _withheld_closed_policy(
    economics: ProfitLockEconomics, threshold: float, persistence: int
) -> dict[str, object]:
    return {
        **_policy_declaration(threshold, persistence),
        "status": "withheld_no_causal_observations",
        "trigger_decision_time_ms": None,
        "exit_reference_price": None,
        "estimated_exit_price": None,
        "estimated_net_pnl_usd": None,
        "actual_net_pnl_usd": economics.actual_net_pnl_usd,
        "estimated_minus_actual_net_usd": None,
    }


def _open_policy(
    side: str,
    entry: Record,
    marked: Record,
    funding: Mapping[int, float],
    observations: Sequence[RegimeLossExitObservation],
    threshold: float,
    persistence: int,
) -> dict[str, object]:
    declaration = _policy_declaration(threshold, persistence)
    if not observations:
        return _unavailable_open_policy(declaration)
    entry_price = _positive_number(entry.get("price"), "open entry price")
    result = evaluate_regime_loss_exit(
        side=side,
        entry_price=entry_price,
        observations=observations,
        loss_threshold_bps=threshold,
        persistence_decisions=persistence,
    )
    if result.state != "triggered":
        return _observing_open_policy(declaration, result)
    estimated_exit, estimated_net, marked_net = _open_exit_economics(
        side, entry, marked, funding, result
    )
    return {
        **declaration,
        **_result_fields(result),
        "status": "would_have_triggered_open_path",
        "estimated_exit_price": estimated_exit,
        "estimated_net_pnl_usd": estimated_net,
        "estimated_minus_current_marked_net_usd": estimated_net - marked_net,
    }


def _open_exit_economics(
    side: str,
    entry: Record,
    marked: Record,
    funding: Mapping[int, float],
    result: RegimeLossExitResult,
) -> tuple[float, float, float]:
    trigger_ms = nonnegative_int(result.trigger_decision_time_ms, "open trigger")
    reference = _positive_number(result.exit_reference_price, "open reference")
    entry_price = _positive_number(entry.get("price"), "open entry price")
    size = _positive_number(entry.get("size"), "open loss-exit size")
    entry_ms = nonnegative_int(entry.get("venue_timestamp_ms"), "open entry time")
    entry_fee = _nonnegative_number(marked.get("fees_usd"), "open entry fee")
    fee_rate = entry_fee / (entry_price * size)
    slippage = abs(number(entry.get("slippage_bps"), "open entry slippage")) / 10_000.0
    estimated_exit = reference * (1.0 - slippage if side == "long" else 1.0 + slippage)
    direction = 1.0 if side == "long" else -1.0
    gross = direction * (estimated_exit - entry_price) * size
    exit_fee = estimated_exit * size * fee_rate
    estimated_net = (
        gross - entry_fee - exit_fee + funding_sum(funding, entry_ms, trigger_ms)
    )
    marked_net = number(
        marked.get("active_lifecycle_marked_net_pnl_usd"), "open marked net PnL"
    )
    return estimated_exit, estimated_net, marked_net


def _unavailable_open_policy(declaration: Record) -> dict[str, object]:
    return {
        **declaration,
        "status": "unavailable_no_causal_observations",
        "trigger_decision_time_ms": None,
        "exit_reference_price": None,
        "estimated_exit_price": None,
        "estimated_net_pnl_usd": None,
        "estimated_minus_current_marked_net_usd": None,
    }


def _observing_open_policy(
    declaration: Record, result: RegimeLossExitResult
) -> dict[str, object]:
    return {
        **declaration,
        **_result_fields(result),
        "status": "observing_not_triggered",
        "estimated_exit_price": None,
        "estimated_net_pnl_usd": None,
        "estimated_minus_current_marked_net_usd": None,
    }


def _policy_declaration(threshold: float, persistence: int) -> dict[str, object]:
    return {
        "policy_id": regime_loss_exit_policy_id(persistence, threshold),
        "persistence_decisions": persistence,
        "opposition_threshold": -0.5,
        "loss_threshold_bps": threshold,
        "signal_clock": "completed_1m_close",
        "execution_reference": "next_1m_open",
    }


def _result_fields(result: RegimeLossExitResult) -> dict[str, object]:
    return {
        "reason": result.reason,
        "trigger_decision_time_ms": result.trigger_decision_time_ms,
        "exit_reference_price": result.exit_reference_price,
        "trigger_close_return_bps": result.trigger_close_return_bps,
        "consecutive_opposed_at_trigger": result.consecutive_opposed_at_trigger,
        "maximum_consecutive_opposed": result.maximum_consecutive_opposed,
        "current_consecutive_opposed": result.current_consecutive_opposed,
        "unavailable_decisions": result.unavailable_decisions,
        "coverage_gap_decisions": result.coverage_gap_decisions,
        "worst_close_return_bps": result.worst_close_return_bps,
    }


def _validate_side(side: str) -> None:
    if side not in {"long", "short"}:
        raise ValueError("loss-exit side must be long or short")


def _positive_number(value: object, label: str) -> float:
    parsed = number(value, label)
    if parsed <= 0.0:
        raise ValueError(f"{label} must be positive")
    return parsed


def _nonnegative_number(value: object, label: str) -> float:
    parsed = number(value, label)
    if parsed < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return parsed
