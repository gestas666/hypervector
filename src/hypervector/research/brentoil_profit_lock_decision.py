"""Prospective, report-only BRENTOIL profit-lock policy disposition."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math


def evaluate_brentoil_profit_locks(
    checkpoint: Mapping[str, object],
    preregistration: Mapping[str, object],
) -> dict[str, object]:
    """Evaluate the frozen policies using only eligible post-boundary closes."""
    contract = _preregistered_contract(preregistration)
    results = _profit_lock_results(checkpoint)
    entry_times = _entry_times(checkpoint)
    eligible, incomplete = _eligible_results(results, entry_times, contract)
    side_coverage = {
        side: sum(row.get("side") == side for row in eligible)
        for side in contract["required_sides"]
    }
    policies = {
        policy_id: _policy_summary(eligible, policy_id, contract["required_sides"])
        for policy_id in contract["policy_ids"]
    }
    eligible_policies = [
        policy_id for policy_id, summary in policies.items() if summary["passed"]
    ]
    passed = bool(eligible_policies)
    return {
        "eligible_lifecycle_ids": [str(row["lifecycle_id"]) for row in eligible],
        "excluded_declared_lifecycle_ids": sorted(contract["excluded_ids"]),
        "excluded_incomplete_candle_lifecycle_ids": incomplete,
        "side_coverage": side_coverage,
        "policies": policies,
        "eligible_policy_ids": eligible_policies,
        "passed": passed,
        "decision": "eligible_for_live_implementation_review"
        if passed
        else "retain_v61_no_lock_collect_both_sides",
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }


def _preregistered_contract(
    preregistration: Mapping[str, object],
) -> dict[str, object]:
    identity = _mapping(preregistration, "live_identity")
    boundary = _mapping(preregistration, "prospective_boundary")
    formation = _mapping(preregistration, "hypothesis_formation_evidence")
    diagnostic = _mapping(preregistration, "exit_policy_diagnostic")
    required_sides = _strings(identity.get("required_sides"), "required sides")
    if set(required_sides) != {"long", "short"}:
        raise ValueError("BRENTOIL required sides must be long and short")
    return {
        "strategy_id": _text(identity.get("signal_strategy_id"), "strategy id"),
        "symbol": _text(identity.get("symbol"), "symbol"),
        "required_sides": required_sides,
        "boundary_ms": _integer(boundary.get("capture_start_ms"), "boundary"),
        "excluded_ids": set(
            _strings(formation.get("excluded_lifecycle_ids"), "excluded ids")
        ),
        "policy_ids": _strings(diagnostic.get("policy_ids"), "policy ids"),
    }


def _profit_lock_results(
    checkpoint: Mapping[str, object],
) -> list[Mapping[str, object]]:
    audit = _mapping(checkpoint, "audit")
    challenger = _mapping(audit, "profit_lock_challenger")
    mechanism = _mapping(challenger, "all_time_live_mechanism")
    return _mappings(mechanism.get("latest_results"), "latest results")


def _entry_times(checkpoint: Mapping[str, object]) -> dict[str, int]:
    audit = _mapping(checkpoint, "audit")
    reflections = _mapping(audit, "trade_reflections")
    history = _mapping(reflections, "all_time_live")
    output: dict[str, int] = {}
    for trade in _mappings(history.get("trades"), "trade reflections"):
        lifecycle_id = _text(trade.get("lifecycle_id"), "lifecycle id")
        entry = _mapping(trade, "entry")
        output[lifecycle_id] = _integer(entry.get("venue_timestamp_ms"), "entry time")
    return output


def _eligible_results(
    results: Sequence[Mapping[str, object]],
    entry_times: Mapping[str, int],
    contract: Mapping[str, object],
) -> tuple[list[Mapping[str, object]], list[str]]:
    eligible: list[Mapping[str, object]] = []
    incomplete: list[str] = []
    for row in results:
        if not _matches_contract(row, entry_times, contract):
            continue
        lifecycle_id = _text(row.get("lifecycle_id"), "lifecycle id")
        if not _complete_candle_coverage(row):
            incomplete.append(lifecycle_id)
            continue
        eligible.append(row)
    return eligible, incomplete


def _matches_contract(
    row: Mapping[str, object],
    entry_times: Mapping[str, int],
    contract: Mapping[str, object],
) -> bool:
    lifecycle_id = _text(row.get("lifecycle_id"), "lifecycle id")
    excluded = contract["excluded_ids"]
    if not isinstance(excluded, set):
        raise RuntimeError("BRENTOIL excluded lifecycle contract is invalid")
    entry_time = entry_times.get(lifecycle_id)
    return (
        row.get("strategy_id") == contract["strategy_id"]
        and row.get("symbol") == contract["symbol"]
        and row.get("status") == "eligible"
        and lifecycle_id not in excluded
        and entry_time is not None
        and entry_time >= int(contract["boundary_ms"])
    )


def _complete_candle_coverage(row: Mapping[str, object]) -> bool:
    expected = row.get("completed_bars_expected")
    observed = row.get("completed_bars_observed")
    return (
        isinstance(expected, int)
        and not isinstance(expected, bool)
        and expected > 0
        and observed == expected
    )


def _policy_summary(
    rows: Sequence[Mapping[str, object]],
    policy_id: str,
    required_sides: Sequence[str],
) -> dict[str, object]:
    deltas_by_side: dict[str, list[float]] = {side: [] for side in required_sides}
    for row in rows:
        side = _text(row.get("side"), "side")
        policies = _mapping(row, "policies")
        policy = _mapping(policies, policy_id)
        delta = _number(
            policy.get("estimated_minus_actual_net_usd"), "policy net delta"
        )
        if side in deltas_by_side:
            deltas_by_side[side].append(delta)
    all_deltas = [delta for values in deltas_by_side.values() for delta in values]
    side_totals = {side: sum(values) for side, values in deltas_by_side.items()}
    leave_largest = sum(all_deltas) - max(all_deltas, default=0.0)
    coverage = all(bool(deltas_by_side[side]) for side in required_sides)
    passed = coverage and all(side_totals[side] > 0.0 for side in required_sides)
    passed = passed and leave_largest > 0.0
    return {
        "lifecycle_count": len(all_deltas),
        "side_counts": {side: len(values) for side, values in deltas_by_side.items()},
        "net_delta_usd_by_side": side_totals,
        "total_net_delta_usd": sum(all_deltas),
        "leave_largest_net_delta_usd": leave_largest,
        "complete_both_side_coverage": coverage,
        "passed": passed,
    }


def _mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"BRENTOIL evidence mapping is missing: {key}")
    return value


def _mappings(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise ValueError(f"BRENTOIL {label} must be a list of objects")
    return list(value)


def _strings(value: object, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise ValueError(f"BRENTOIL {label} must be non-empty strings")
    return list(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"BRENTOIL {label} must be non-empty")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"BRENTOIL {label} must be a positive integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"BRENTOIL {label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"BRENTOIL {label} must be finite")
    return number
