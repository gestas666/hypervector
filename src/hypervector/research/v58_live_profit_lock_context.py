"""Validated prospective profit-lock context for open V58 lifecycles."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite

Record = Mapping[str, object]
_POLICIES = {
    "a25_floor15_trail10": (25.0, 15.0, 10.0),
    "a40_floor15_trail20": (40.0, 15.0, 20.0),
    "a60_floor15_trail30": (60.0, 15.0, 30.0),
}
_STATES = {
    "not_activated",
    "armed_not_triggered",
    "triggered_before_current_boundary",
    "withheld_incomplete_candle_coverage",
}


def extract_v58_live_profit_lock_challenger(trade: Record) -> dict[str, object]:
    """Project predeclared counterfactual exits without claiming actual fills."""
    raw = trade.get("open_profit_lock_challenger")
    if raw is None:
        return _unavailable()
    challenger = _mapping(raw, "profit-lock challenger")
    _require_contract(challenger)
    policies = _mapping(challenger.get("policies"), "profit-lock policies")
    if set(policies) != set(_POLICIES):
        raise ValueError("V58 live profit-lock policy set is inconsistent")
    expected = _nonnegative_integer(
        challenger.get("completed_bars_expected"), "expected bars"
    )
    observed = _nonnegative_integer(
        challenger.get("completed_bars_observed"), "observed bars"
    )
    if observed > expected:
        raise ValueError("V58 live profit-lock bar coverage is inconsistent")
    status = _text(challenger.get("status"), "profit-lock status")
    _require_status_coverage(status, expected, observed)
    return {
        "status": status,
        "policy_origin": _text(challenger.get("policy_origin"), "policy origin"),
        "as_of_timestamp_ms": _positive_integer(
            challenger.get("as_of_timestamp_ms"), "as-of time"
        ),
        "completed_bars_expected": expected,
        "completed_bars_observed": observed,
        "policies": {
            policy_id: _policy_payload(
                policy_id, _mapping(policies[policy_id], policy_id)
            )
            for policy_id in _POLICIES
        },
        "actual_exit_fill_claim": False,
        "execution_authority": "none",
    }


def _require_status_coverage(status: str, expected: int, observed: int) -> None:
    complete_status = "observed" if expected else "awaiting_completed_bar"
    required = (
        complete_status if observed == expected else "insufficient_candle_coverage"
    )
    if status != required:
        raise ValueError("V58 live profit-lock status and coverage disagree")


def _require_contract(challenger: Record) -> None:
    expected = {
        "schema_version": 2,
        "mode": "cohort_open_profit_lock_challenger_v2",
        "policy_origin": "existing_predeclared_hype_profit_research_v1",
    }
    if any(challenger.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 live profit-lock identity is inconsistent")
    contract = _mapping(challenger.get("contract"), "profit-lock contract")
    required = {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "automatic_promotion": False,
    }
    if any(contract.get(key) != value for key, value in required.items()):
        raise ValueError("V58 live profit-lock authority is invalid")


def _policy_payload(policy_id: str, policy: Record) -> dict[str, object]:
    activation, floor, giveback = _POLICIES[policy_id]
    expected = {
        "policy_id": policy_id,
        "activation_bps": activation,
        "floor_bps": floor,
        "trailing_giveback_bps": giveback,
    }
    if any(policy.get(key) != value for key, value in expected.items()):
        raise ValueError(f"V58 live profit-lock {policy_id} declaration differs")
    state = _text(policy.get("status"), f"{policy_id} status")
    if state not in _STATES:
        raise ValueError(f"V58 live profit-lock {policy_id} status is invalid")
    output: dict[str, object] = {
        "activation_bps": activation,
        "floor_bps": floor,
        "trailing_giveback_bps": giveback,
        "status": state,
        "trigger_timestamp_ms": _trigger_timestamp(policy, state),
    }
    output.update(_economics_payload(policy, state))
    return output


def _trigger_timestamp(policy: Record, state: str) -> int | None:
    value = policy.get("trigger_timestamp_ms")
    if state == "triggered_before_current_boundary":
        return _positive_integer(value, "profit-lock trigger time")
    if value is not None:
        raise ValueError("V58 inactive profit-lock unexpectedly has a trigger")
    return None


def _economics_payload(policy: Record, state: str) -> dict[str, object]:
    economics = _mapping(
        policy.get("counterfactual_economics"), "profit-lock economics"
    )
    if state not in {"triggered_before_current_boundary", "armed_not_triggered"}:
        if economics.get("status") != "unavailable":
            raise ValueError("V58 inactive profit-lock economics are success-shaped")
        return {}
    expected_status = (
        "estimated_trigger_exit"
        if state == "triggered_before_current_boundary"
        else "estimated_active_stop_exit"
    )
    if economics.get("status") != expected_status:
        raise ValueError("V58 live profit-lock economics status is inconsistent")
    if economics.get("funding_included") is not False:
        raise ValueError("V58 live profit-lock must not claim funding inclusion")
    if economics.get("additional_slippage_included") is not False:
        raise ValueError("V58 live profit-lock must not claim extra slippage")
    return {
        "estimated_net_pnl_excluding_funding_usd": _number(
            economics.get("estimated_net_pnl_excluding_funding_usd"), "estimated net"
        ),
        "estimated_minus_current_exit_net_excluding_funding_usd": _number(
            economics.get("estimated_minus_current_exit_net_excluding_funding_usd"),
            "estimated delta",
        ),
        "funding_included": False,
        "additional_slippage_included": False,
    }


def _unavailable() -> dict[str, object]:
    return {
        "status": "unavailable_source_missing",
        "reason": "open_profit_lock_challenger_missing",
        "policies": {},
        "actual_exit_fill_claim": False,
        "execution_authority": "none",
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 live {label} must be a mapping")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"V58 live {label} must be non-empty text")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 live {label} must be numeric")
    output = float(value)
    if not isfinite(output):
        raise ValueError(f"V58 live {label} must be finite")
    return output


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"V58 live {label} must be a nonnegative integer")
    return value


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"V58 live {label} must be a positive integer")
    return value
