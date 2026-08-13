"""Causal observer for lifecycle-bound provider exits ignored by live policy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from hypervector.research.cohort_live_audit_values import (
    mapping,
    nonnegative_int,
    number,
    payload,
    text,
)
from hypervector.research.cohort_open_trade_path import build_open_trade_path

Record = Mapping[str, object]
PolicyIndex = dict[tuple[str, int], str]


class CandleLike(Protocol):
    """Minimum completed-candle interface required by the path projector."""

    timestamp_ms: int
    high: float
    low: float
    close: float


def build_ignored_provider_exit_observer(
    evaluations: Sequence[Record],
    candles: Mapping[int, CandleLike],
    *,
    side: str,
    entry: Record,
    marked_economics: Record,
    exit_plan: Record,
    as_of_ms: int,
) -> dict[str, object]:
    """Measure what followed the first same-side exit ignored by policy."""
    direction = _direction(side)
    entry_ms = nonnegative_int(entry.get("venue_timestamp_ms"), "entry timestamp")
    observed_ms = nonnegative_int(as_of_ms, "ignored exit observation timestamp")
    if observed_ms < entry_ms:
        raise ValueError("ignored exit observation cannot precede entry")
    policy = text(
        exit_plan.get("provider_recipe_exit_policy"),
        "provider recipe exit policy",
    )
    if policy not in {"ignore", "honor"}:
        raise ValueError("provider recipe exit policy must be ignore or honor")
    if policy == "honor":
        return _empty("not_applicable_policy_honors", policy)
    matching = _matching_evaluations(evaluations, side, entry_ms, observed_ms)
    if not matching:
        return _empty("no_ignored_exit_observed", policy)
    first = matching[0]
    decision_ms = nonnegative_int(first.get("decision_time_ms"), "exit decision time")
    reference = _positive(first.get("reference_price"), "exit reference price")
    signal = _signal(first, direction, entry)
    synthetic_entry = {"venue_timestamp_ms": decision_ms + 1, "price": reference}
    return {
        **_base("observed", policy, len(matching)),
        "first_signal": signal,
        "path_since_first_signal": build_open_trade_path(
            candles,
            side,
            synthetic_entry,
            marked_economics,
            observed_ms,
        ),
    }


def build_provider_exit_policy_index(
    asset_records: Mapping[str, Sequence[Record]],
) -> PolicyIndex:
    """Recover the immutable bound recipe-exit policy for each entry order."""
    output: PolicyIndex = {}
    for symbol, records in asset_records.items():
        for record in records:
            if record.get("event_type") != "state_transition":
                continue
            values = payload(record)
            if values.get("entry_oid") is None or values.get("execution_plan") is None:
                continue
            oid = nonnegative_int(values.get("entry_oid"), "execution plan entry oid")
            if oid < 1:
                raise ValueError("execution plan entry oid must be positive")
            plan = mapping(values.get("execution_plan"), "bound execution plan")
            policy = _provider_policy(plan.get("provider_recipe_exit_policy", "ignore"))
            key = (symbol, oid)
            prior = output.get(key)
            if prior is not None and prior != policy:
                raise ValueError(f"{symbol}:{oid} changed provider recipe exit policy")
            output[key] = policy
    return output


def build_closed_ignored_provider_exit_outcome(
    evaluations: Sequence[Record],
    candles: Mapping[int, CandleLike],
    *,
    side: str,
    entry: Record,
    exit_leg: Record,
    provider_recipe_exit_policy: str | None,
    actual_economics: Record,
) -> dict[str, object]:
    """Retain ignored-exit evidence beside the authoritative actual close."""
    actual_exit = _actual_exit(exit_leg, actual_economics)
    if provider_recipe_exit_policy is None:
        return {
            **_closed_base("unavailable_bound_policy", None),
            "first_signal": None,
            "ignored_signal_count": 0,
            "path_from_first_signal_to_actual_exit": None,
            "gross_continuation_from_signal_bps": None,
            "counterfactual_signal_exit_net_pnl_usd": None,
            "actual_exit": actual_exit,
        }
    policy = _provider_policy(provider_recipe_exit_policy)
    observer = build_ignored_provider_exit_observer(
        evaluations,
        candles,
        side=side,
        entry=entry,
        marked_economics={"mark_price": actual_exit["price"]},
        exit_plan={"provider_recipe_exit_policy": policy},
        as_of_ms=int(actual_exit["venue_timestamp_ms"]),
    )
    path = observer["path_since_first_signal"]
    continuation = (
        None
        if path is None
        else mapping(path, "closed ignored-exit path").get(
            "current_directional_return_bps"
        )
    )
    return {
        **_closed_base(text(observer.get("status"), "observer status"), policy),
        "first_signal": observer["first_signal"],
        "ignored_signal_count": observer["ignored_signal_count"],
        "path_from_first_signal_to_actual_exit": path,
        "gross_continuation_from_signal_bps": continuation,
        "counterfactual_signal_exit_net_pnl_usd": None,
        "actual_exit": actual_exit,
    }


def _matching_evaluations(
    evaluations: Sequence[Record],
    side: str,
    entry_ms: int,
    as_of_ms: int,
) -> list[Record]:
    matches: list[Record] = []
    for evaluation in evaluations:
        decision_ms = nonnegative_int(
            evaluation.get("decision_time_ms"), "provider evaluation time"
        )
        sides = _exit_sides(evaluation.get("exit_sides"))
        if entry_ms < decision_ms <= as_of_ms and side in sides:
            _positive(evaluation.get("reference_price"), "exit reference price")
            text(evaluation.get("exit_reason"), "provider exit reason")
            matches.append(evaluation)
    return sorted(matches, key=lambda row: int(row["decision_time_ms"]))


def _exit_sides(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError("provider exit_sides must be a sequence")
    sides = tuple(text(item, "provider exit side") for item in value)
    if any(side not in {"long", "short"} for side in sides):
        raise ValueError("provider exit_sides contains an unsupported side")
    return sides


def _signal(evaluation: Record, direction: float, entry: Record) -> dict[str, object]:
    reference = _positive(evaluation.get("reference_price"), "exit reference price")
    entry_price = _positive(entry.get("price"), "entry price")
    return {
        "decision_time_ms": nonnegative_int(
            evaluation.get("decision_time_ms"), "exit decision time"
        ),
        "reference_price": reference,
        "entry_directional_return_bps": _directional_bps(
            direction, entry_price, reference
        ),
        "exit_reason": text(evaluation.get("exit_reason"), "provider exit reason"),
        "decision_action": evaluation.get("decision_action"),
        "readiness": dict(mapping(evaluation.get("readiness"), "exit readiness")),
    }


def _empty(status: str, policy: str) -> dict[str, object]:
    return {
        **_base(status, policy, 0),
        "first_signal": None,
        "path_since_first_signal": None,
    }


def _base(status: str, policy: str, count: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "ignored_provider_recipe_exit_observer_v1",
        "status": status,
        "provider_recipe_exit_policy": policy,
        "ignored_signal_count": count,
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
            "automatic_promotion": False,
        },
        "limitations": [
            "signal reference prices are not counterfactual venue fills",
            "path evidence excludes future funding, fees, and exit slippage",
            "the observer cannot retain, close, resize, or route a lifecycle",
        ],
    }


def _direction(side: str) -> float:
    value = text(side, "open trade side")
    if value not in {"long", "short"}:
        raise ValueError("open trade side must be long or short")
    return 1.0 if value == "long" else -1.0


def _positive(value: object, label: str) -> float:
    parsed = number(value, label)
    if parsed <= 0.0:
        raise ValueError(f"{label} must be positive")
    return parsed


def _directional_bps(direction: float, entry: float, price: float) -> float:
    return direction * (price / entry - 1.0) * 10_000.0


def _provider_policy(value: object) -> str:
    policy = text(value, "provider recipe exit policy")
    if policy not in {"ignore", "honor"}:
        raise ValueError("provider recipe exit policy must be ignore or honor")
    return policy


def _actual_exit(exit_leg: Record, economics: Record) -> dict[str, object]:
    fee = number(economics.get("fees_usd"), "actual lifecycle fees")
    if fee < 0.0:
        raise ValueError("actual lifecycle fees must be nonnegative")
    reason = economics.get("exit_reason")
    return {
        "venue_timestamp_ms": nonnegative_int(
            exit_leg.get("venue_timestamp_ms"), "actual exit timestamp"
        ),
        "price": _positive(exit_leg.get("price"), "actual exit price"),
        "net_pnl_usd": number(economics.get("net_pnl_usd"), "actual net pnl"),
        "fees_usd": fee,
        "funding_usd": number(economics.get("funding_usd"), "actual funding"),
        "exit_reason": None if reason is None else text(reason, "actual exit reason"),
        "exit_controller_strategy_id": text(
            economics.get("exit_controller_strategy_id"),
            "actual exit controller",
        ),
    }


def _closed_base(status: str, policy: str | None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "closed_ignored_provider_recipe_exit_outcome_v1",
        "status": status,
        "provider_recipe_exit_policy": policy,
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
            "automatic_promotion": False,
            "actual_exit_is_authoritative": True,
        },
        "limitations": [
            "signal reference price is not a counterfactual venue fill",
            "counterfactual signal-exit fees and slippage are unavailable",
            "gross continuation does not establish after-cost policy superiority",
        ],
    }
