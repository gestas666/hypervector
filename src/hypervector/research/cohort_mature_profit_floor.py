"""Late-activation, floor-only profit preservation research."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_profit_lock_lifecycle import (
    build_profit_lock_lifecycle_results,
)
from hypervector.research.cohort_open_profit_lock_challenger import (
    build_open_profit_lock_challenger,
)
from hypervector.research.cohort_profit_lock_mechanism import (
    build_normalized_profit_lock_report,
)
from hypervector.research.cohort_profit_lock_policy import (
    CandleLike,
    ProfitLockPolicy,
    policy_declaration,
)

Record = Mapping[str, object]
_FLOOR_BPS = 25.0
_TRAIL_DISABLED_BPS = 10_000.0

MATURE_PROFIT_FLOOR_POLICIES = (
    ProfitLockPolicy("a100_floor25_only", 100.0, _FLOOR_BPS, _TRAIL_DISABLED_BPS),
    ProfitLockPolicy("a250_floor25_only", 250.0, _FLOOR_BPS, _TRAIL_DISABLED_BPS),
    ProfitLockPolicy("a500_floor25_only", 500.0, _FLOOR_BPS, _TRAIL_DISABLED_BPS),
)


def build_mature_profit_floor_mechanism(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    reflected_trades: Sequence[Record],
) -> dict[str, object]:
    """Evaluate coarse mature-profit floors without continuous trailing."""
    results = build_profit_lock_lifecycle_results(
        cohort_records,
        asset_records,
        reflected_trades,
        policies=MATURE_PROFIT_FLOOR_POLICIES,
    )
    report = build_normalized_profit_lock_report(
        results,
        policies=[
            policy_declaration(policy) for policy in MATURE_PROFIT_FLOOR_POLICIES
        ],
        contract=_contract(),
        limitations=_limitations(),
    )
    report.update(
        {
            "mode": "cohort_mature_profit_floor_mechanism_v1",
            "mechanism": "floor_only_after_completed_bar_activation",
            "policy_origin": "post_hoc_spcx_open_winner_hypothesis_20260813",
            "continuous_trailing_enabled": False,
            "trail_disabled_by_giveback_bps": _TRAIL_DISABLED_BPS,
        }
    )
    return report


def build_open_mature_profit_floor_challenger(
    candles: Mapping[int, CandleLike],
    side: str,
    entry: Record,
    marked_economics: Record,
    as_of_ms: int,
) -> dict[str, object]:
    """Expose current floor-only state without changing the live position."""
    report = build_open_profit_lock_challenger(
        candles,
        side,
        entry,
        marked_economics,
        as_of_ms,
        policies=MATURE_PROFIT_FLOOR_POLICIES,
    )
    report.update(
        {
            "mode": "cohort_open_mature_profit_floor_challenger_v1",
            "policy_origin": "post_hoc_spcx_open_winner_hypothesis_20260813",
            "continuous_trailing_enabled": False,
            "trail_disabled_by_giveback_bps": _TRAIL_DISABLED_BPS,
            "limitations": _limitations(),
        }
    )
    return report


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "portfolio_pnl_claimed": False,
    }


def _limitations() -> list[str]:
    return [
        "the policy family was specified after observing an open SPCX winner",
        "activation levels are coarse hypotheses and were not optimized",
        "the 25bps gross floor cannot guarantee positive net PnL after gaps and costs",
        "activation and stop updates use prior completed one-minute bars",
        "gap-through triggers use the adverse bar open rather than the stale floor",
        "missing holding candles withhold a lifecycle instead of assuming no trigger",
        "overlapping lifecycles are not a counterfactual shared-portfolio equity path",
        "this report cannot gate, size, route, close, or submit a trade",
    ]
