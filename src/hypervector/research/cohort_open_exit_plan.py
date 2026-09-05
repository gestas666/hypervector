"""Authoritative timer and profit-lock projection for open lifecycles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

from hypervector.live.cohort_execution_plan_validation import (
    CohortExecutionPlanError,
    validate_profit_lock_contract,
)
from hypervector.research.cohort_live_audit_values import (
    mapping,
    mapping_list,
    nonnegative_int,
    payload,
    text,
)

Record = Mapping[str, object]
_OPPOSITE_EXIT_SCOPE = "selected_opposite_from_any_executable_provider_same_symbol"
_OPPOSITE_EXIT_ARBITRATION = "regime_then_priority"


@dataclass(frozen=True)
class _ExitContract:
    soft_seconds: int
    policy: str
    hard_seconds: int | None
    recipe_exit_policy: str
    profit_lock_policy: str
    activation_bps: float | None
    floor_bps: float | None
    giveback_bps: float | None
    source: str


def build_open_exit_plan(
    symbol: str,
    strategy: str,
    entry: Record,
    as_of_ms: int,
    records: Sequence[Record],
    regime_context: str,
    runtime_opened_at_ms: int | None,
) -> dict[str, object]:
    """Project one open lifecycle's exact configured exit contract."""
    contract = _exit_contract(symbol, strategy, records)
    entry_ms = nonnegative_int(entry.get("venue_timestamp_ms"), "entry timestamp")
    opened_at_ms = (
        runtime_opened_at_ms if runtime_opened_at_ms is not None else entry_ms
    )
    if opened_at_ms > as_of_ms:
        raise ValueError(f"{symbol} runtime timer starts after the checkpoint")
    deadlines = _deadline_values(contract, opened_at_ms, as_of_ms, regime_context)
    return {
        "maximum_hold_seconds": contract.soft_seconds,
        "maximum_hold_policy": contract.policy,
        "hard_maximum_hold_seconds": contract.hard_seconds,
        "opened_at_ms": opened_at_ms,
        "timer_origin": _timer_origin(runtime_opened_at_ms),
        **deadlines,
        "regime_context": regime_context,
        "source": contract.source,
        "controller": "cohort_maximum_hold",
        "opposite_intent_exit_scope": _OPPOSITE_EXIT_SCOPE,
        "opposite_intent_arbitration": _OPPOSITE_EXIT_ARBITRATION,
        "provider_recipe_exit_policy": contract.recipe_exit_policy,
        "profit_lock_policy": contract.profit_lock_policy,
        "profit_lock_activation_bps": contract.activation_bps,
        "profit_lock_floor_bps": contract.floor_bps,
        "profit_lock_giveback_bps": contract.giveback_bps,
    }


def _deadline_values(
    contract: _ExitContract,
    opened_at_ms: int,
    as_of_ms: int,
    regime_context: str,
) -> dict[str, object]:
    soft_deadline = opened_at_ms + contract.soft_seconds * 1_000
    hard_deadline = (
        None
        if contract.hard_seconds is None
        else opened_at_ms + contract.hard_seconds * 1_000
    )
    extension = (
        contract.policy == "extend_while_regime_supported"
        and regime_context == "still_directionally_supported"
        and as_of_ms >= soft_deadline
        and hard_deadline is not None
        and as_of_ms < hard_deadline
    )
    deadline = hard_deadline if extension else soft_deadline
    return {
        "soft_deadline_timestamp_ms": soft_deadline,
        "hard_deadline_timestamp_ms": hard_deadline,
        "deadline_timestamp_ms": deadline,
        "remaining_time_ms": max(0, deadline - as_of_ms),
        "expired": as_of_ms >= deadline,
        "extension_active": extension,
    }


def _exit_contract(
    symbol: str,
    strategy: str,
    records: Sequence[Record],
) -> _ExitContract:
    identity = _single_event(records, "configuration_identity")
    configured = _asset_row(payload(identity), symbol, "configured assets")
    snapshot = next(
        (
            row
            for row in reversed(records)
            if row.get("event_type") == "cohort_snapshot"
        ),
        None,
    )
    if snapshot is not None:
        observed = _asset_row(payload(snapshot), symbol, "snapshot assets")
        raw_plan = observed.get("execution_plan")
        if raw_plan is not None:
            plan = mapping(raw_plan, f"{symbol} bound execution plan")
            if text(plan.get("strategy_id"), "execution plan strategy") != strategy:
                raise ValueError(f"{symbol} execution plan strategy mismatch")
            return _parse_contract(plan, symbol, "bound_execution_plan")
    return _parse_contract(configured, symbol, "asset_runtime_default")


def _parse_contract(values: Record, symbol: str, source: str) -> _ExitContract:
    soft = _positive_seconds(values, symbol)
    policy = text(values.get("maximum_hold_policy", "fixed"), "maximum hold policy")
    hard = _optional_seconds(values.get("hard_maximum_hold_seconds"), symbol)
    if policy == "fixed" and hard is not None:
        raise ValueError(f"{symbol} fixed maximum hold cannot define a hard deadline")
    if policy == "extend_while_regime_supported" and (hard is None or hard <= soft):
        raise ValueError(f"{symbol} hard maximum hold must follow its soft deadline")
    if policy not in {"fixed", "extend_while_regime_supported"}:
        raise ValueError(f"{symbol} maximum hold policy is unsupported")
    recipe = text(
        values.get("provider_recipe_exit_policy", "ignore"), "recipe exit policy"
    )
    if recipe not in {"ignore", "honor"}:
        raise ValueError(f"{symbol} provider recipe exit policy is unsupported")
    lock = _parse_profit_lock(values, symbol)
    return _ExitContract(soft, policy, hard, recipe, *lock, source)


def _parse_profit_lock(
    values: Record,
    symbol: str,
) -> tuple[str, float | None, float | None, float | None]:
    policy = text(values.get("profit_lock_policy", "none"), "profit lock policy")
    raw_values = (
        values.get("profit_lock_activation_bps"),
        values.get("profit_lock_floor_bps"),
        values.get("profit_lock_giveback_bps"),
    )
    parsed = tuple(
        None if value is None else _positive_number(value, f"{symbol} profit lock")
        for value in raw_values
    )
    activation, floor, giveback = parsed
    try:
        validate_profit_lock_contract(policy, activation, floor, giveback)
    except CohortExecutionPlanError as exc:
        raise ValueError(f"{symbol} profit lock contract is invalid: {exc}") from exc
    return policy, activation, floor, giveback


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return number


def _single_event(records: Sequence[Record], event_type: str) -> Record:
    matches = [row for row in records if row.get("event_type") == event_type]
    if len(matches) != 1:
        raise ValueError(f"open trade reflections require one {event_type}")
    return matches[0]


def _asset_row(values: Record, symbol: str, label: str) -> Record:
    matches = [
        row
        for row in mapping_list(values.get("assets"), label)
        if row.get("symbol") == symbol
    ]
    if len(matches) != 1:
        raise ValueError(f"{symbol} requires one {label} row")
    return matches[0]


def _positive_seconds(values: Record, symbol: str) -> int:
    seconds = nonnegative_int(
        values.get("maximum_hold_seconds"), f"{symbol} maximum hold"
    )
    if seconds < 1:
        raise ValueError(f"{symbol} maximum hold must be positive")
    return seconds


def _optional_seconds(value: object, symbol: str) -> int | None:
    return (
        None if value is None else nonnegative_int(value, f"{symbol} hard maximum hold")
    )


def _timer_origin(runtime_opened_at_ms: int | None) -> str:
    return (
        "persisted_runtime_opened_at"
        if runtime_opened_at_ms is not None
        else "venue_entry_fill_fallback_legacy"
    )
