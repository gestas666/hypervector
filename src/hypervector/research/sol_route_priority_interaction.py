"""Report-only SOL provider-priority interaction replay."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.current_cohort_shared_portfolio import CohortOutcome
from hypervector.research.evidence_selected_portfolio import (
    PrioritizedPortfolioConfig,
    PrioritizedPortfolioReport,
    replay_prioritized_outcomes,
)

HULK_STRATEGY = "hulk_expansion_bidirectional_tuned_v2"
RANGE_STRATEGY = "range_onset_bidirectional_v1"
BREAKOUT_STRATEGY = "hype_breakout_onset_bidirectional_v1"
CURRENT_STATIC_PRIORITY = (BREAKOUT_STRATEGY, RANGE_STRATEGY, HULK_STRATEGY)
RANGE_FIRST_STATIC_PRIORITY = (RANGE_STRATEGY, BREAKOUT_STRATEGY, HULK_STRATEGY)
_STRATEGIES = frozenset(CURRENT_STATIC_PRIORITY)
_ARMS = {
    "current_static_priority": CURRENT_STATIC_PRIORITY,
    "range_first_static_priority": RANGE_FIRST_STATIC_PRIORITY,
}


def build_sol_route_priority_interaction(
    outcomes: tuple[CohortOutcome, ...],
    *,
    development_end_ms: int,
    opened_final_start_ms: int,
    opened_final_end_ms: int,
    source_evidence: Mapping[str, object],
    initial_equity_usd: float = 500.0,
) -> dict[str, object]:
    """Compare two frozen priority arms without execution authority."""
    _validate_contract(outcomes, source_evidence, initial_equity_usd)
    partitions = _partition(
        outcomes,
        development_end_ms,
        opened_final_start_ms,
        opened_final_end_ms,
    )
    return {
        "schema_version": 1,
        "mode": "sol_route_priority_interaction_v1",
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "contract": _contract(initial_equity_usd),
        "boundaries": _boundaries(
            development_end_ms,
            opened_final_start_ms,
            opened_final_end_ms,
        ),
        "trial_accounting": _trial_accounting(),
        "input_trade_counts": {key: len(value) for key, value in partitions.items()},
        "development": _phase_report(
            partitions["development"], initial_equity_usd, used=True
        ),
        "opened_final_confirmation": _phase_report(
            partitions["opened_final_confirmation"],
            initial_equity_usd,
            used=False,
        ),
        "source_evidence": dict(source_evidence),
        "decision": "report_only_no_automatic_priority_change",
        "limitations": _limitations(),
    }


def _partition(
    outcomes: tuple[CohortOutcome, ...],
    development_end_ms: int,
    final_start_ms: int,
    final_end_ms: int,
) -> dict[str, tuple[CohortOutcome, ...]]:
    _validate_boundaries(development_end_ms, final_start_ms, final_end_ms)
    development = tuple(
        row
        for row in outcomes
        if row.outcome.entry_time_ms < development_end_ms
        and row.outcome.exit_time_ms < development_end_ms
    )
    final = tuple(
        row
        for row in outcomes
        if final_start_ms <= row.outcome.entry_time_ms < final_end_ms
        and row.outcome.exit_time_ms < final_end_ms
    )
    selected = {row.trade_id for row in development + final}
    purged = tuple(row for row in outcomes if row.trade_id not in selected)
    return {
        "development": development,
        "opened_final_confirmation": final,
        "purged_or_out_of_scope": purged,
    }


def _phase_report(
    outcomes: tuple[CohortOutcome, ...],
    initial_equity_usd: float,
    *,
    used: bool,
) -> dict[str, object]:
    return {
        "used_for_selection": used,
        "input_trades": len(outcomes),
        "input_by_strategy_side": _input_counts(outcomes),
        "arms": {
            name: _arm_report(outcomes, priority, initial_equity_usd)
            for name, priority in _ARMS.items()
        },
    }


def _arm_report(
    outcomes: tuple[CohortOutcome, ...],
    priority: tuple[str, ...],
    initial_equity_usd: float,
) -> dict[str, object]:
    if not outcomes:
        return _empty_arm(priority, initial_equity_usd)
    replay = replay_prioritized_outcomes(
        outcomes,
        PrioritizedPortfolioConfig(initial_equity_usd, 1, priority),
    )
    accepted_values = [row.net_pnl_usd for row in replay.accepted]
    return {
        "priority": list(priority),
        "performance": replay.to_dict(),
        "accepted_by_strategy": _accepted_counts(replay),
        "rejected_by_strategy_reason": _rejected_counts(replay),
        "net_pnl_excluding_largest_winner_usd": _net_ex_largest(accepted_values),
    }


def _accepted_counts(report: PrioritizedPortfolioReport) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in report.accepted:
        counts[row.strategy_id] = counts.get(row.strategy_id, 0) + 1
    return dict(sorted(counts.items()))


def _rejected_counts(report: PrioritizedPortfolioReport) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in report.rejected:
        key = f"{row.strategy_id}|{row.reason}"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _input_counts(outcomes: Sequence[CohortOutcome]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in outcomes:
        key = f"{row.strategy_id}|{row.side}"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _net_ex_largest(values: Sequence[float]) -> float | None:
    if not values:
        return None
    largest = max((value for value in values if value > 0.0), default=0.0)
    return sum(values) - largest


def _empty_arm(priority: tuple[str, ...], equity: float) -> dict[str, object]:
    return {
        "priority": list(priority),
        "performance": {
            "initial_equity_usd": equity,
            "final_equity_usd": equity,
            "net_pnl_usd": 0.0,
            "completed_trades": 0,
        },
        "accepted_by_strategy": {},
        "rejected_by_strategy_reason": {},
        "net_pnl_excluding_largest_winner_usd": None,
    }


def _validate_contract(
    outcomes: tuple[CohortOutcome, ...],
    evidence: Mapping[str, object],
    initial_equity_usd: float,
) -> None:
    if not outcomes or {row.strategy_id for row in outcomes} != _STRATEGIES:
        raise ValueError("SOL priority replay requires all three exact strategies")
    if any(row.outcome.symbol != "SOL" for row in outcomes):
        raise ValueError("SOL priority replay accepts only SOL outcomes")
    if not evidence:
        raise ValueError("SOL priority replay requires source evidence")
    if initial_equity_usd <= 0.0:
        raise ValueError("SOL priority replay equity must be positive")


def _validate_boundaries(development: int, start: int, end: int) -> None:
    if any(isinstance(value, bool) or value < 0 for value in (development, start, end)):
        raise ValueError("SOL priority boundaries must be nonnegative integers")
    if not development < start < end:
        raise ValueError("SOL priority boundaries must be strictly ordered")


def _contract(initial_equity_usd: float) -> dict[str, object]:
    return {
        "initial_equity_usd": initial_equity_usd,
        "symbol": "SOL",
        "maximum_positions": 1,
        "one_position_per_symbol": True,
        "open_lifecycle_eviction": False,
        "static_fallback_only": True,
        "live_regime_arbitration_reproduced": False,
    }


def _boundaries(development: int, start: int, end: int) -> dict[str, int]:
    return {
        "development_end_exclusive_ms": development,
        "opened_final_start_ms": start,
        "opened_final_end_exclusive_ms": end,
    }


def _trial_accounting() -> dict[str, object]:
    return {
        "priority_arms": 2,
        "priority_orders_tested": [
            list(CURRENT_STATIC_PRIORITY),
            list(RANGE_FIRST_STATIC_PRIORITY),
        ],
        "parameter_sweeps": 0,
    }


def _limitations() -> list[str]:
    return [
        "the opened final block was previously inspected and is descriptive",
        "static priority does not reproduce live regime-aware arbitration",
        "source routes were selected through prior heterogeneous experiments",
        "normalized historical fills cannot reproduce private IOC queue position",
        "priority evidence cannot route, size, enter, close, or evict a live trade",
    ]
