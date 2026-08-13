"""Report-only economics of closed maximum-hold extensions."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.research.cohort_lifecycle_evidence import (
    SIZE_TOLERANCE,
    FillAggregate,
    build_fill_index,
    build_funding_index,
    funding_sum,
    positive_int,
    positive_number,
    required_fill,
)
from hypervector.research.cohort_live_audit_values import (
    mapping,
    nonnegative_int,
    number,
    payload,
    text,
)
from hypervector.research.cohort_maximum_hold_extension_contract import (
    extension_outcome_contract,
    extension_outcome_limitations,
)
from hypervector.research.cohort_open_trade_path import (
    build_open_trade_extension_path,
)
from hypervector.research.cohort_post_soft_trail_challenger import (
    build_post_soft_trail_challenger,
)
from hypervector.research.cohort_trade_reflections import (
    build_reflection_evidence_index,
)

Record = Mapping[str, object]
_LATEST_LIMIT = 50
_MONEY_TOLERANCE = 0.000_005
_MIN_INFERRED_EXTENSION_MS = 60_000


@dataclass(frozen=True)
class _BoundPlan:
    strategy_id: str
    opened_at_ms: int
    soft_seconds: int
    policy: str
    hard_seconds: int | None


def build_maximum_hold_extension_outcomes(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    reflected_trades: Sequence[Record],
) -> dict[str, object]:
    """Compare actual extended exits with a causal soft-deadline reference."""
    plans = _bound_plan_index(asset_records)
    fills = build_fill_index(asset_records)
    funding = build_funding_index(asset_records)
    decisions = _decision_index(cohort_records)
    evidence = build_reflection_evidence_index(cohort_records)
    outcomes = [
        _resolve_outcome(trade, plan, fills, funding, decisions, evidence.candles)
        for trade in reflected_trades
        if (plan := plans.get(_trade_identity(trade))) is not None
        and plan.policy == "extend_while_regime_supported"
        and _is_extension_outcome(trade, plan, decisions)
    ]
    outcomes.sort(key=_exit_timestamp)
    return {
        "schema_version": 1,
        "mode": "cohort_maximum_hold_extension_outcomes",
        "contract": extension_outcome_contract(),
        "summary": _summary(outcomes),
        "by_provider_symbol": _grouped_summary(outcomes),
        "latest_outcomes": outcomes[-_LATEST_LIMIT:],
        "post_soft_trail_challenger": build_post_soft_trail_challenger(
            outcomes, reflected_trades, evidence.candles, funding
        ),
        "limitations": extension_outcome_limitations(),
    }


def _bound_plan_index(
    asset_records: Mapping[str, Sequence[Record]],
) -> dict[tuple[str, int], _BoundPlan]:
    plans: dict[tuple[str, int], _BoundPlan] = {}
    for symbol, rows in asset_records.items():
        validated_symbol = text(symbol, "asset symbol")
        for row in rows:
            if row.get("event_type") != "state_transition":
                continue
            values = payload(row)
            if values.get("execution_plan") is None:
                continue
            if values.get("entry_oid") is None:
                continue
            oid = positive_int(values.get("entry_oid"), "execution-plan entry oid")
            plan = _parse_plan(values, validated_symbol)
            key = (validated_symbol, oid)
            prior = plans.get(key)
            if prior is not None and prior != plan:
                raise ValueError(
                    f"{validated_symbol}:{oid} has conflicting bound execution plan"
                )
            plans[key] = plan
    return plans


def _parse_plan(values: Record, symbol: str) -> _BoundPlan:
    plan = mapping(values.get("execution_plan"), f"{symbol} execution plan")
    policy = text(plan.get("maximum_hold_policy", "fixed"), "maximum-hold policy")
    if policy not in {"fixed", "extend_while_regime_supported"}:
        raise ValueError(f"{symbol} execution plan has unsupported maximum-hold policy")
    soft = positive_int(plan.get("maximum_hold_seconds"), "soft maximum hold")
    hard_value = plan.get("hard_maximum_hold_seconds")
    hard = None if hard_value is None else positive_int(hard_value, "hard maximum hold")
    if policy == "fixed" and hard is not None:
        raise ValueError(f"{symbol} fixed maximum hold cannot define a hard deadline")
    if policy == "extend_while_regime_supported" and (hard is None or hard <= soft):
        raise ValueError(f"{symbol} extension hard deadline must follow soft deadline")
    return _BoundPlan(
        text(plan.get("strategy_id"), "execution-plan strategy"),
        nonnegative_int(values.get("opened_at_ms"), "runtime opened_at_ms"),
        soft,
        policy,
        hard,
    )


def _decision_index(records: Sequence[Record]) -> dict[str, str]:
    decisions: dict[str, str] = {}
    for row in records:
        if row.get("event_type") != "maximum_hold_decision":
            continue
        values = payload(row)
        stage = text(values.get("decision_stage", "soft"), "maximum-hold stage")
        if stage == "terminal":
            continue
        if stage != "soft":
            raise ValueError("maximum-hold decision stage is unsupported")
        lifecycle = text(values.get("lifecycle_id"), "maximum-hold lifecycle")
        outcome = text(values.get("outcome"), "maximum-hold outcome")
        if outcome not in {"extend", "exit"}:
            raise ValueError("maximum-hold decision outcome is unsupported")
        prior = decisions.get(lifecycle)
        if prior is not None and prior != outcome:
            raise ValueError(f"{lifecycle} has conflicting maximum-hold decisions")
        decisions[lifecycle] = outcome
    return decisions


def _resolve_outcome(
    trade: Record,
    plan: _BoundPlan,
    fills: Mapping[tuple[str, int], FillAggregate],
    funding: Mapping[str, Mapping[int, float]],
    decisions: Mapping[str, str],
    candles: Mapping[str, Mapping[int, object]],
) -> dict[str, object]:
    identity = _trade_identity(trade)
    symbol, entry_oid = identity
    lifecycle = text(trade.get("lifecycle_id"), "trade lifecycle")
    strategy = text(trade.get("strategy_id"), "trade strategy")
    if strategy != plan.strategy_id:
        raise ValueError(f"{lifecycle} strategy conflicts with its bound plan")
    side = _side(trade.get("side"))
    entry = mapping(trade.get("entry"), "trade entry")
    exit_leg = mapping(trade.get("exit"), "trade exit")
    exit_oid = positive_int(trade.get("exit_oid"), "trade exit oid")
    entry_fill = required_fill(fills, identity, entry, "entry", "extension")
    exit_fill = required_fill(fills, (symbol, exit_oid), exit_leg, "exit", "extension")
    soft_ms = plan.opened_at_ms + plan.soft_seconds * 1_000
    path = build_open_trade_extension_path(
        candles.get(symbol, {}),
        side,
        soft_deadline_ms=soft_ms,
        marked_economics={"mark_price": exit_leg.get("price")},
        as_of_ms=nonnegative_int(exit_leg.get("venue_timestamp_ms"), "exit timestamp"),
    )
    baseline = positive_number(path.get("baseline_price"), "soft reference price")
    economics = _counterfactual_economics(
        trade, side, entry_fill, exit_fill, baseline, funding.get(symbol, {}), soft_ms
    )
    return {
        **_outcome_identity(
            lifecycle, symbol, strategy, side, entry_oid, exit_oid, plan, exit_leg
        ),
        "causal_decision_recorded": lifecycle in decisions,
        "decision_outcome": decisions.get(lifecycle),
        "soft_reference_price": baseline,
        "counterfactual_method": (
            "last_completed_boundary_close_x_actual_exit_fill_reference_ratio"
        ),
        **economics,
        "path_since_soft_deadline": path,
    }


def _outcome_identity(
    lifecycle: str,
    symbol: str,
    strategy: str,
    side: str,
    entry_oid: int,
    exit_oid: int,
    plan: _BoundPlan,
    exit_leg: Record,
) -> dict[str, object]:
    exit_ms = nonnegative_int(exit_leg.get("venue_timestamp_ms"), "exit timestamp")
    soft_ms = plan.opened_at_ms + plan.soft_seconds * 1_000
    if plan.hard_seconds is None:
        raise ValueError("extended lifecycle lacks a hard maximum hold")
    return {
        "status": "resolved",
        "lifecycle_id": lifecycle,
        "symbol": symbol,
        "strategy_id": strategy,
        "side": side,
        "entry_oid": entry_oid,
        "exit_oid": exit_oid,
        "opened_at_ms": plan.opened_at_ms,
        "soft_deadline_timestamp_ms": soft_ms,
        "hard_deadline_timestamp_ms": plan.opened_at_ms + plan.hard_seconds * 1_000,
        "actual_exit_timestamp_ms": exit_ms,
        "extension_duration_ms": exit_ms - soft_ms,
        "evidence_basis": "persisted_runtime_plan_plus_resolved_execution",
    }


def _counterfactual_economics(
    trade: Record,
    side: str,
    entry_fill: FillAggregate,
    exit_fill: FillAggregate,
    soft_reference: float,
    funding: Mapping[int, float],
    soft_ms: int,
) -> dict[str, object]:
    entry = mapping(trade.get("entry"), "trade entry")
    exit_leg = mapping(trade.get("exit"), "trade exit")
    entry_ms = nonnegative_int(entry.get("venue_timestamp_ms"), "entry timestamp")
    exit_ms = nonnegative_int(exit_leg.get("venue_timestamp_ms"), "exit timestamp")
    entry_price = positive_number(entry.get("price"), "entry price")
    exit_price = positive_number(exit_leg.get("price"), "exit price")
    reference = positive_number(
        exit_leg.get("expected_reference_price"), "exit reference price"
    )
    size = positive_number(entry.get("size"), "entry size")
    _validate_recorded_costs(
        trade, side, size, entry_price, exit_price, entry_fill, exit_fill
    )
    actual_funding = number(trade.get("funding_usd"), "actual funding")
    observed_full = funding_sum(funding, entry_ms, exit_ms)
    if not math.isclose(observed_full, actual_funding, abs_tol=_MONEY_TOLERANCE):
        raise ValueError("extension funding rows do not reconcile to actual lifecycle")
    soft_funding = funding_sum(funding, entry_ms, soft_ms)
    estimated_soft_exit = soft_reference * exit_price / reference
    exit_fee_rate = exit_fill.fee_usd / exit_fill.notional_usd
    estimated_soft_fee = estimated_soft_exit * size * exit_fee_rate
    direction = 1.0 if side == "long" else -1.0
    actual_gross = direction * (exit_price - entry_price) * size
    soft_gross = direction * (estimated_soft_exit - entry_price) * size
    actual_net = number(trade.get("net_pnl_usd"), "actual net PnL")
    computed_actual = (
        actual_gross - entry_fill.fee_usd - exit_fill.fee_usd + actual_funding
    )
    if not math.isclose(computed_actual, actual_net, abs_tol=_MONEY_TOLERANCE):
        raise ValueError("extension economics do not reconcile to actual net PnL")
    soft_net = soft_gross - entry_fill.fee_usd - estimated_soft_fee + soft_funding
    return {
        "estimated_soft_exit_price": estimated_soft_exit,
        "entry_fee_usd": entry_fill.fee_usd,
        "actual_exit_fee_usd": exit_fill.fee_usd,
        "estimated_soft_exit_fee_usd": estimated_soft_fee,
        "funding_through_soft_usd": soft_funding,
        "funding_during_extension_usd": actual_funding - soft_funding,
        "actual_gross_pnl_usd": actual_gross,
        "estimated_soft_gross_pnl_usd": soft_gross,
        "actual_net_pnl_usd": actual_net,
        "estimated_soft_net_pnl_usd": soft_net,
        "actual_minus_soft_gross_usd": actual_gross - soft_gross,
        "actual_minus_soft_net_usd": actual_net - soft_net,
    }


def _validate_recorded_costs(
    trade: Record,
    side: str,
    size: float,
    entry_price: float,
    exit_price: float,
    entry_fill: FillAggregate,
    exit_fill: FillAggregate,
) -> None:
    exit_size = positive_number(
        mapping(trade.get("exit"), "trade exit").get("size"), "exit size"
    )
    if not all(
        math.isclose(observed, size, abs_tol=SIZE_TOLERANCE)
        for observed in (entry_fill.size, exit_fill.size, exit_size)
    ):
        raise ValueError("extension fill sizes do not reconcile to lifecycle size")
    recorded_fees = number(trade.get("fees_usd"), "actual fees")
    if not math.isclose(
        entry_fill.fee_usd + exit_fill.fee_usd,
        recorded_fees,
        abs_tol=_MONEY_TOLERANCE,
    ):
        raise ValueError("extension fill fees do not reconcile to lifecycle fees")
    if side not in {"long", "short"} or min(entry_price, exit_price) <= 0.0:
        raise ValueError("extension side or prices are invalid")


def _trade_identity(trade: Record) -> tuple[str, int]:
    symbol = text(trade.get("symbol"), "trade symbol")
    oid = positive_int(trade.get("entry_oid"), "trade entry oid")
    if trade.get("lifecycle_id") != f"{symbol}:{oid}":
        raise ValueError("trade lifecycle identity is inconsistent")
    return symbol, oid


def _is_extension_outcome(
    trade: Record,
    plan: _BoundPlan,
    decisions: Mapping[str, str],
) -> bool:
    exit_leg = mapping(trade.get("exit"), "trade exit")
    exit_ms = nonnegative_int(exit_leg.get("venue_timestamp_ms"), "exit timestamp")
    duration_ms = exit_ms - (plan.opened_at_ms + plan.soft_seconds * 1_000)
    decision = decisions.get(text(trade.get("lifecycle_id"), "trade lifecycle"))
    if decision is not None:
        return decision == "extend" and duration_ms > 0
    return duration_ms >= _MIN_INFERRED_EXTENSION_MS


def _exit_timestamp(outcome: Record) -> int:
    return nonnegative_int(
        outcome.get("actual_exit_timestamp_ms"), "actual exit timestamp"
    )


def _side(value: object) -> str:
    side = text(value, "trade side")
    if side not in {"long", "short"}:
        raise ValueError("trade side must be long or short")
    return side


def _summary(outcomes: Sequence[Record]) -> dict[str, object]:
    deltas = [
        number(row.get("actual_minus_soft_net_usd"), "extension delta")
        for row in outcomes
    ]
    return {
        "bound_extension_lifecycles": len(outcomes),
        "resolved": len(outcomes),
        "inferred_without_decision_event": sum(
            row.get("causal_decision_recorded") is False for row in outcomes
        ),
        "better_than_soft_reference": sum(value > 0.0 for value in deltas),
        "worse_than_soft_reference": sum(value < 0.0 for value in deltas),
        "unchanged_from_soft_reference": sum(value == 0.0 for value in deltas),
        "actual_net_pnl_usd": sum(
            number(row.get("actual_net_pnl_usd"), "actual net") for row in outcomes
        ),
        "estimated_soft_net_pnl_usd": sum(
            number(row.get("estimated_soft_net_pnl_usd"), "soft net")
            for row in outcomes
        ),
        "actual_minus_soft_net_usd": sum(deltas),
    }


def _grouped_summary(outcomes: Sequence[Record]) -> dict[str, object]:
    grouped: dict[str, list[Record]] = {}
    for row in outcomes:
        key = f"{row['strategy_id']}|{row['symbol']}"
        grouped.setdefault(key, []).append(row)
    return {key: _summary(rows) for key, rows in sorted(grouped.items())}
