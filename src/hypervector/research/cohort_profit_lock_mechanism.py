"""Normalized all-live summaries for report-only profit-lock mechanisms."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import mapping, number
from hypervector.research.cohort_profit_lock_robustness import (
    build_profit_lock_robustness_by_policy,
)

Record = Mapping[str, object]
_LATEST_LIMIT = 50


def build_normalized_profit_lock_report(
    results: Sequence[Record],
    *,
    policies: Sequence[Record],
    contract: Record,
    limitations: Sequence[str],
) -> dict[str, object]:
    """Describe price-relative exit mechanics without pooling unlike sizing contracts."""
    return _normalized_report(
        results,
        policies=policies,
        contract=contract,
        limitations=limitations,
        mode="cohort_profit_lock_normalized_mechanism_v1",
        policy_origin="existing_predeclared_hype_profit_research_v1",
    )


def build_normalized_regime_conditioned_profit_lock_report(
    results: Sequence[Record],
    *,
    policies: Sequence[Record],
    contract: Record,
    activation_contract: Record,
    limitations: Sequence[str],
) -> dict[str, object]:
    """Describe profit locks armed only after persistent causal regime opposition."""
    report = _normalized_report(
        results,
        policies=policies,
        contract=contract,
        limitations=limitations,
        mode="cohort_regime_conditioned_profit_lock_mechanism_v1",
        policy_origin="post_hoc_regime_opposition_hypothesis_20260806",
    )
    report["activation_contract"] = dict(activation_contract)
    return report


def build_normalized_support_decay_profit_lock_report(
    results: Sequence[Record],
    *,
    policies: Sequence[Record],
    contract: Record,
    activation_contract: Record,
    limitations: Sequence[str],
) -> dict[str, object]:
    """Describe profit locks armed only after persistent causal support decay."""
    report = _normalized_report(
        results,
        policies=policies,
        contract=contract,
        limitations=limitations,
        mode="cohort_support_decay_profit_lock_mechanism_v1",
        policy_origin="post_hoc_open_sol_profit_giveback_hypothesis_20260807",
    )
    report["activation_contract"] = dict(activation_contract)
    return report


def _normalized_report(
    results: Sequence[Record],
    *,
    policies: Sequence[Record],
    contract: Record,
    limitations: Sequence[str],
    mode: str,
    policy_origin: str,
) -> dict[str, object]:
    policy_ids = tuple(str(policy["policy_id"]) for policy in policies)
    profiles = {str(row["source_profile_fingerprint"]) for row in results}
    runs = {str(row["source_run_id"]) for row in results}
    return {
        "schema_version": 1,
        "mode": mode,
        "scope": "all_live_history_normalized_mechanism",
        "contract": dict(contract),
        "policy_origin": policy_origin,
        "policies": [dict(policy) for policy in policies],
        "profile_contracts_may_differ": True,
        "source_profile_count": len(profiles),
        "source_run_count": len(runs),
        "summary_by_policy": _summaries(results, policy_ids),
        "robustness_by_policy": build_profit_lock_robustness_by_policy(
            results, policy_ids
        ),
        "by_provider_symbol": _grouped(results, policy_ids),
        "by_provider_symbol_side": _grouped(results, policy_ids, by_side=True),
        "latest_results": list(results[-_LATEST_LIMIT:]),
        "limitations": [
            *limitations,
            "source profiles, sizing, leverage, and execution policies may differ",
            "basis-point summaries normalize each lifecycle by its own entry notional",
            "normalized mechanism evidence is not current-profile portfolio PnL",
        ],
    }


def _grouped(
    results: Sequence[Record],
    policy_ids: Sequence[str],
    *,
    by_side: bool = False,
) -> dict[str, object]:
    grouped: dict[str, list[Record]] = {}
    for row in results:
        key = f"{row['strategy_id']}|{row['symbol']}"
        if by_side:
            key = f"{key}|{row['side']}"
        grouped.setdefault(key, []).append(row)
    return {
        key: {
            "summary_by_policy": _summaries(rows, policy_ids),
            "robustness_by_policy": build_profit_lock_robustness_by_policy(
                rows, policy_ids
            ),
        }
        for key, rows in sorted(grouped.items())
    }


def _summaries(
    results: Sequence[Record], policy_ids: Sequence[str]
) -> dict[str, object]:
    return {policy_id: _summary(results, policy_id) for policy_id in policy_ids}


def _summary(results: Sequence[Record], policy_id: str) -> dict[str, object]:
    eligible: list[tuple[float, float]] = []
    triggered = 0
    for result in results:
        policy = mapping(mapping(result["policies"], "policies")[policy_id], policy_id)
        if str(policy.get("status", "")).startswith("withheld_"):
            continue
        notional = number(result.get("entry_notional_usd"), "entry notional")
        if notional <= 0.0:
            raise ValueError("profit-lock entry notional must be positive")
        estimated = number(policy.get("estimated_net_pnl_usd"), "estimated net")
        actual = number(policy.get("actual_net_pnl_usd"), "actual net")
        eligible.append((estimated / notional * 10_000.0, actual / notional * 10_000.0))
        triggered += policy.get("status") == "triggered"
    estimated_bps = [estimated for estimated, _ in eligible]
    actual_bps = [actual for _, actual in eligible]
    delta_bps = [estimated - actual for estimated, actual in eligible]
    losses = -sum(value for value in estimated_bps if value < 0.0)
    gains = sum(value for value in estimated_bps if value > 0.0)
    return {
        "lifecycles": len(results),
        "eligible_lifecycles": len(eligible),
        "withheld_lifecycles": len(results) - len(eligible),
        "triggered": triggered,
        "wins": sum(value > 0.0 for value in estimated_bps),
        "losses": sum(value < 0.0 for value in estimated_bps),
        "mean_estimated_net_return_bps": _mean(estimated_bps),
        "mean_actual_net_return_bps": _mean(actual_bps),
        "mean_delta_net_return_bps": _mean(delta_bps),
        "normalized_profit_factor": gains / losses if losses else None,
    }


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None
