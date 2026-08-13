"""Summaries and report contract for dual-MTF reversal-exit evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import median

from hypervector.research.cohort_live_audit_values import mapping, number, text

Record = Mapping[str, object]
_ZERO_TOLERANCE = 1e-12


def summarize_dual_mtf_reversal_results(
    rows: Sequence[Record], *, policy_id: str
) -> dict[str, object]:
    """Summarize one declared policy without omitting retained actual exits."""
    policy = text(policy_id, "dual-MTF policy id")
    eligible = [row for row in rows if row.get("status") == "eligible"]
    withheld = [row for row in rows if row.get("status") != "eligible"]
    all_actuals = [
        number(row.get("actual_net_pnl_usd"), "all lifecycle actual net")
        for row in rows
    ]
    withheld_actuals = [
        number(row.get("actual_net_pnl_usd"), "withheld actual net") for row in withheld
    ]
    candidates, actuals, triggered = _policy_values(eligible, policy)
    wins = [value for value in candidates if value > _ZERO_TOLERANCE]
    losses = [value for value in candidates if value < -_ZERO_TOLERANCE]
    candidate_total = sum(candidates)
    return {
        "policy_id": policy,
        "eligible_lifecycles": len(eligible),
        "withheld_lifecycles": len(rows) - len(eligible),
        "triggered_lifecycles": triggered,
        "retained_actual_lifecycles": len(eligible) - triggered,
        "actual_net_pnl_usd": sum(actuals),
        "eligible_actual_net_pnl_usd": sum(actuals),
        "withheld_actual_net_pnl_usd": sum(withheld_actuals),
        "all_lifecycle_actual_net_pnl_usd": sum(all_actuals),
        "candidate_net_pnl_usd": candidate_total,
        "candidate_minus_actual_net_usd": candidate_total - sum(actuals),
        "candidate_wins": len(wins),
        "candidate_losses": len(losses),
        "candidate_breakeven": len(candidates) - len(wins) - len(losses),
        "candidate_profit_factor": _profit_factor(wins, losses, candidates),
        "candidate_median_net_pnl_usd": median(candidates) if candidates else None,
        "actual_median_net_pnl_usd": median(actuals) if actuals else None,
        "candidate_net_excluding_largest_winner_usd": _excluding_largest_winner(
            candidates
        ),
    }


def build_dual_mtf_reversal_report(
    results: Sequence[Record],
    episodes: dict[str, object],
    policy_ids: Sequence[str],
    surface: Sequence[int],
    run_id: str,
    profile: str,
) -> dict[str, object]:
    """Build the complete authority-none challenger report."""
    return {
        "schema_version": 1,
        "mode": "cohort_dual_mtf_profit_reversal_exit_challenger_v1",
        "contract": _contract(),
        "persistence_surface": list(surface),
        "trial_count": len(surface),
        "all_live": _summaries(results, policy_ids),
        "current_profile": _scoped_summary(
            results, policy_ids, "source_profile_fingerprint", profile
        ),
        "current_run": _scoped_summary(results, policy_ids, "source_run_id", run_id),
        "by_provider_symbol": _grouped_summaries(
            results, policy_ids, ("strategy_id", "symbol")
        ),
        "by_side": _grouped_summaries(results, policy_ids, ("side",)),
        "current_run_effective_episodes": _episode_summaries(
            episodes, results, policy_ids
        ),
        "closed_lifecycles": list(results),
        "limitations": _limitations(),
    }


def _policy_values(
    rows: Sequence[Record], policy: str
) -> tuple[list[float], list[float], int]:
    candidates: list[float] = []
    actuals: list[float] = []
    triggered = 0
    for row in rows:
        policies = mapping(row.get("policies"), "policies")
        result = mapping(policies.get(policy), policy)
        candidates.append(number(result.get("estimated_net_pnl_usd"), "candidate net"))
        actuals.append(number(row.get("actual_net_pnl_usd"), "actual net"))
        triggered += int(result.get("status") == "triggered")
    return candidates, actuals, triggered


def _summaries(rows: Sequence[Record], policies: Sequence[str]) -> dict[str, object]:
    return {
        policy: summarize_dual_mtf_reversal_results(rows, policy_id=policy)
        for policy in policies
    }


def _scoped_summary(
    rows: Sequence[Record], policies: Sequence[str], field: str, value: str
) -> dict[str, object]:
    scoped = [row for row in rows if row.get(field) == value]
    return {field: value, "policies": _summaries(scoped, policies)}


def _grouped_summaries(
    rows: Sequence[Record], policies: Sequence[str], fields: tuple[str, ...]
) -> dict[str, object]:
    groups: dict[str, list[Record]] = {}
    for row in rows:
        key = "|".join(text(row.get(field), field) for field in fields)
        groups.setdefault(key, []).append(row)
    return {key: _summaries(values, policies) for key, values in groups.items()}


def _episode_summaries(
    episodes: dict[str, object], rows: Sequence[Record], policies: Sequence[str]
) -> dict[str, object]:
    by_id = {text(row.get("lifecycle_id"), "lifecycle"): row for row in rows}
    enriched = []
    for cluster in episodes["clusters"]:
        value = mapping(cluster, "episode")
        lifecycles = [by_id[item] for item in value["lifecycle_ids"] if item in by_id]
        enriched.append(
            {**value, "closed_policy_summaries": _summaries(lifecycles, policies)}
        )
    return {**episodes, "clusters": enriched}


def _profit_factor(
    wins: Sequence[float], losses: Sequence[float], all_values: Sequence[float]
) -> float | None:
    gross_loss = abs(sum(losses))
    return (
        None
        if not all_values or gross_loss <= _ZERO_TOLERANCE
        else sum(wins) / gross_loss
    )


def _excluding_largest_winner(values: Sequence[float]) -> float | None:
    if not values:
        return None
    winner = max((value for value in values if value > _ZERO_TOLERANCE), default=0.0)
    return sum(values) - winner


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_promotion": False,
        "selected_policy": None,
        "performance_gate": False,
    }


def _limitations() -> list[str]:
    return [
        "the three persistence cells are jointly reported and none is selected",
        "cost clearance uses prior completed-close PnL with entry fee rate and accrued funding",
        "candidate exits use the next open plus adverse absolute entry-slippage as a proxy",
        "candidate execution is estimated and is not a private venue fill",
        "missing decisions reset persistence and missing prices are counted",
        "overlap episodes are reported; raw lifecycles are not independent samples",
        "open positions remain in live forward evidence and are not scored as closed outcomes here",
        "small post-hoc samples cannot establish an exit edge",
        "this report cannot route, size, close, or submit a trade",
    ]
