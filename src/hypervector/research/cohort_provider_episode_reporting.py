"""Bounded summaries for provider episode and re-entry evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from statistics import median

from hypervector.research.cohort_provider_episode_values import (
    number,
    optional_mapping,
    optional_number,
    row_number,
    row_text,
)

Record = Mapping[str, object]


def resolved_economics(trade: Record) -> dict[str, object]:
    """Extract required resolved lifecycle economics."""
    return {
        "net_pnl_usd": number(trade.get("net_pnl_usd"), "net pnl"),
        "net_return_on_margin_pct": number(
            trade.get("net_return_on_margin_pct"), "net return on margin"
        ),
    }


def marked_economics(trade: Record) -> dict[str, object]:
    """Extract optional open marks without treating them as resolved PnL."""
    marked = optional_mapping(trade.get("marked_economics"), "marked economics")
    pnl = optional_number(marked.get("active_lifecycle_marked_net_pnl_usd"))
    margin = optional_number(marked.get("margin_used_usd"))
    if margin is not None and margin <= 0.0:
        raise ValueError("open marked margin must be positive")
    return {
        "marked_net_pnl_usd": pnl,
        "marked_return_on_margin_pct": (
            pnl / margin * 100.0 if pnl is not None and margin else None
        ),
    }


def build_resolved_report(
    rows: Sequence[dict[str, object]],
) -> dict[str, object]:
    """Separate first and repeat resolved economics by exact route-side."""
    attributed = [row for row in rows if row["attribution_status"] == "attributed"]
    first = [row for row in attributed if row["entry_class"] == "first_entry"]
    repeat = [row for row in attributed if row["entry_class"] == "repeat_entry"]
    grouped: defaultdict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(
        list
    )
    for row in rows:
        key = (
            row_text(row, "strategy_id"),
            row_text(row, "symbol"),
            row_text(row, "side"),
        )
        grouped[key].append(row)
    return {
        "matching_trades": len(rows),
        "attributable": len(attributed),
        "unavailable": len(rows) - len(attributed),
        "first_entries": len(first),
        "repeat_entries": len(repeat),
        "net_pnl_includes_open_marks": False,
        "first_entry": _outcome(first),
        "repeat_entry": _outcome(repeat),
        "by_provider_symbol_side": {
            "|".join(key): _resolved_pair(value)
            for key, value in sorted(grouped.items())
        },
    }


def _resolved_pair(rows: Sequence[dict[str, object]]) -> dict[str, object]:
    attributed = [row for row in rows if row["attribution_status"] == "attributed"]
    first = [row for row in attributed if row["entry_class"] == "first_entry"]
    repeat = [row for row in attributed if row["entry_class"] == "repeat_entry"]
    episode_counts = Counter(row_text(row, "episode_id") for row in attributed)
    return {
        "matching_trades": len(rows),
        "attributable": len(attributed),
        "unavailable": len(rows) - len(attributed),
        "episodes_with_entries": len(episode_counts),
        "episodes_with_reentries": sum(value > 1 for value in episode_counts.values()),
        "first_entry": _outcome(first),
        "repeat_entry": _outcome(repeat),
        "lifecycles": list(rows),
    }


def _outcome(rows: Sequence[dict[str, object]]) -> dict[str, object]:
    pnl = [row_number(row, "net_pnl_usd") for row in rows]
    returns = [row_number(row, "net_return_on_margin_pct") for row in rows]
    gains = sum(value for value in pnl if value > 0.0)
    losses = -sum(value for value in pnl if value < 0.0)
    largest = max((value for value in pnl if value > 0.0), default=0.0)
    return {
        "trades": len(rows),
        "wins": sum(value > 0.0 for value in pnl),
        "losses": sum(value < 0.0 for value in pnl),
        "breakeven": sum(value == 0.0 for value in pnl),
        "net_pnl_usd": sum(pnl),
        "mean_net_return_on_margin_pct": sum(returns) / len(returns)
        if returns
        else None,
        "median_net_return_on_margin_pct": median(returns) if returns else None,
        "usd_profit_factor": gains / losses if losses > 0.0 else None,
        "net_pnl_ex_largest_winner_usd": sum(pnl) - largest,
    }


def build_open_report(rows: Sequence[dict[str, object]]) -> dict[str, object]:
    """Retain provisional marked paths outside resolved economics."""
    attributed = [row for row in rows if row["attribution_status"] == "attributed"]
    marked = [row for row in rows if row.get("marked_net_pnl_usd") is not None]
    return {
        "matching_positions": len(rows),
        "attributable": len(attributed),
        "unavailable": len(rows) - len(attributed),
        "pooled_with_resolved": False,
        "marked_economics_coverage": {
            "available": len(marked),
            "unavailable": len(rows) - len(marked),
        },
        "positions": list(rows),
    }


def build_coverage(
    raw: int,
    deduplicated_count: int,
    unavailable: int,
    technical_boundaries: int,
    missing: int,
    episode_run_counts: Sequence[int],
    profile_resets: int,
    gap_resets: int,
) -> dict[str, int]:
    """Summarize exact decision and continuity coverage."""
    return {
        "matching_rows": raw,
        "deduplicated_decisions": deduplicated_count,
        "unavailable_rows": unavailable,
        "technical_boundary_rows": technical_boundaries,
        "episodes": len(episode_run_counts),
        "restart_spanning_episodes": sum(value > 1 for value in episode_run_counts),
        "profile_boundary_resets": profile_resets,
        "data_gap_resets": gap_resets,
        "routing_rows_without_evaluations": missing,
    }


def report_contract() -> dict[str, object]:
    """Return the immutable no-authority research contract."""
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_strategy_changes": False,
        "runtime_strategy_changed": False,
        "execution_gate": False,
        "portfolio_pnl_claimed": False,
    }


def report_limitations() -> list[str]:
    """Disclose the evidence boundary of the attribution."""
    return [
        "ordinals cover reflected live lifecycles rather than hypothetical missed entries",
        "missing legacy provider decisions remain unavailable rather than inferred",
        "open marked paths remain provisional and are not pooled with resolved economics",
        "profile changes and missing decision bars terminate episode continuity",
        "small first/repeat cohorts are descriptive and cannot establish durable edge",
    ]
