"""Outlier and source-diversity diagnostics for profit-lock mechanisms."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean, median

from hypervector.research.cohort_live_audit_values import mapping, number, text

Record = Mapping[str, object]


@dataclass(frozen=True)
class _PolicyObservation:
    delta_bps: float
    source_run_id: str
    source_profile: str
    triggered: bool


def build_profit_lock_robustness_by_policy(
    results: Sequence[Record],
    policy_ids: Sequence[str],
) -> dict[str, object]:
    """Measure sign, outlier sensitivity, and source diversity by policy."""
    return {
        policy_id: _policy_robustness(results, policy_id) for policy_id in policy_ids
    }


def _policy_robustness(
    results: Sequence[Record],
    policy_id: str,
) -> dict[str, object]:
    rows = tuple(results)
    observations = tuple(
        observation
        for result in rows
        if (observation := _observation(result, policy_id)) is not None
    )
    triggered = tuple(row for row in observations if row.triggered)
    return {
        "lifecycles": len(rows),
        "eligible_lifecycles": len(observations),
        "withheld_lifecycles": len(rows) - len(observations),
        "triggered_lifecycles": len(triggered),
        "distinct_source_runs": len({row.source_run_id for row in observations}),
        "distinct_source_profiles": len({row.source_profile for row in observations}),
        "all_eligible_delta_net_return_bps": _statistics(observations),
        "triggered_delta_net_return_bps": _statistics(triggered),
    }


def _observation(result: Record, policy_id: str) -> _PolicyObservation | None:
    policies = mapping(result.get("policies"), "profit-lock policies")
    policy = mapping(policies.get(policy_id), f"profit-lock policy {policy_id}")
    status = text(policy.get("status"), "profit-lock policy status")
    if status.startswith("withheld_"):
        return None
    notional = number(result.get("entry_notional_usd"), "profit-lock entry notional")
    if notional <= 0.0:
        raise ValueError("profit-lock entry notional must be positive")
    estimated = number(policy.get("estimated_net_pnl_usd"), "estimated net")
    actual = number(policy.get("actual_net_pnl_usd"), "actual net")
    return _PolicyObservation(
        delta_bps=(estimated - actual) / notional * 10_000.0,
        source_run_id=text(result.get("source_run_id"), "profit-lock source run"),
        source_profile=text(
            result.get("source_profile_fingerprint"),
            "profit-lock source profile",
        ),
        triggered=status == "triggered",
    )


def _statistics(observations: Sequence[_PolicyObservation]) -> dict[str, object]:
    values = tuple(row.delta_bps for row in observations)
    ordered = sorted(values)
    return {
        "count": len(values),
        "positive_count": sum(value > 0.0 for value in values),
        "negative_count": sum(value < 0.0 for value in values),
        "zero_count": sum(value == 0.0 for value in values),
        "positive_fraction": (
            sum(value > 0.0 for value in values) / len(values) if values else None
        ),
        "mean": fmean(values) if values else None,
        "median": median(values) if values else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "mean_excluding_most_favorable": (
            fmean(ordered[:-1]) if len(ordered) > 1 else None
        ),
        "mean_excluding_most_adverse": (
            fmean(ordered[1:]) if len(ordered) > 1 else None
        ),
    }
