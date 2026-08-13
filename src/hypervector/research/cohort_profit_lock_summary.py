"""Aggregate report-only profit-lock lifecycle results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import mapping, number

Record = Mapping[str, object]


def summaries(
    results: Sequence[Record], policy_ids: Sequence[str]
) -> dict[str, object]:
    """Summarize every frozen policy over one lifecycle partition."""
    return {policy_id: _policy_summary(results, policy_id) for policy_id in policy_ids}


def grouped_summaries(
    results: Sequence[Record], policy_ids: Sequence[str]
) -> dict[str, object]:
    """Partition frozen-policy economics by provider and symbol."""
    grouped: dict[str, list[Record]] = {}
    for row in results:
        grouped.setdefault(f"{row['strategy_id']}|{row['symbol']}", []).append(row)
    return {
        key: {"summary_by_policy": summaries(rows, policy_ids)}
        for key, rows in sorted(grouped.items())
    }


def _policy_summary(results: Sequence[Record], policy_id: str) -> dict[str, object]:
    policies = [
        mapping(mapping(row["policies"], "policies")[policy_id], policy_id)
        for row in results
    ]
    eligible = [
        row
        for row in policies
        if not str(row.get("status", "")).startswith("withheld_")
    ]
    estimated = [
        number(row.get("estimated_net_pnl_usd"), "estimated net") for row in eligible
    ]
    actual = [number(row.get("actual_net_pnl_usd"), "actual net") for row in eligible]
    losses = -sum(value for value in estimated if value < 0.0)
    gains = sum(value for value in estimated if value > 0.0)
    return {
        "lifecycles": len(results),
        "eligible_lifecycles": len(eligible),
        "withheld_lifecycles": len(results) - len(eligible),
        "triggered": sum(row.get("status") == "triggered" for row in eligible),
        "wins": sum(value > 0.0 for value in estimated),
        "losses": sum(value < 0.0 for value in estimated),
        "estimated_net_pnl_usd": sum(estimated),
        "actual_net_pnl_usd": sum(actual),
        "estimated_minus_actual_net_usd": sum(estimated) - sum(actual),
        "profit_factor": gains / losses if losses else None,
    }
