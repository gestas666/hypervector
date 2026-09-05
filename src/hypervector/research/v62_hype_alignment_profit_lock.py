"""V62 report-only review of one HYPE aligned-route profit lock."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import pandas as pd

from hypervector.research.hype_breakout_exit_experiment import (
    HypePolicyDevelopment,
    develop_hype_exit_policy,
)
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
)

_CONTROL_ID = "aligned_live_exit_control"
_CANDIDATE_ID = "a60_floor15_trail30"


@dataclass(frozen=True)
class V62HypeProfitLockReview:
    """Authority-free report and exact lifecycle rows for the V62 review."""

    report: dict[str, object]
    trade_rows: pd.DataFrame


def v62_candidate_orderbook_coverage(
    trade_rows: pd.DataFrame,
    audit_rows: pd.DataFrame,
) -> dict[str, object]:
    """Join exact A60 entries to locally audited 0xArchive book windows."""
    identity = ["side", "signal_time_utc", "entry_time_utc"]
    required_audit = {
        *identity,
        "status",
        "causal_covered",
        "execution_covered",
        "first_post_entry_delay_ms",
    }
    if {"policy_id", *identity}.difference(trade_rows.columns):
        raise ValueError("V62 HYPE trade rows lack exact entry identity")
    if required_audit.difference(audit_rows.columns):
        raise ValueError("V62 HYPE orderbook audit rows are incomplete")
    candidate = trade_rows.loc[
        trade_rows["policy_id"].eq(_CANDIDATE_ID), identity
    ].copy()
    audit = audit_rows.loc[:, list(required_audit)].copy()
    if candidate.empty or candidate.duplicated(identity).any():
        raise ValueError("V62 HYPE candidate entry identities must be unique")
    if audit.duplicated(identity).any():
        raise ValueError("V62 HYPE orderbook audit identities must be unique")
    for column in identity[1:]:
        candidate[column] = pd.to_datetime(candidate[column], utc=True)
        audit[column] = pd.to_datetime(audit[column], utc=True)
    joined = candidate.merge(audit, how="left", on=identity, validate="one_to_one")
    matched = joined["status"].notna()
    delays = pd.to_numeric(joined["first_post_entry_delay_ms"], errors="coerce")
    statuses = joined.loc[matched, "status"].astype(str).value_counts().to_dict()
    causal = int(joined["causal_covered"].eq(True).sum())
    executable = int(joined["execution_covered"].eq(True).sum())
    return {
        "candidate_lifecycles": len(candidate),
        "matched_audit_rows": int(matched.sum()),
        "causal_covered_rows": causal,
        "execution_covered_rows": executable,
        "status_counts": {str(key): int(value) for key, value in statuses.items()},
        "maximum_first_post_entry_delay_ms": (
            int(delays.max()) if delays.notna().any() else None
        ),
        "complete_candidate_entry_coverage": executable == len(candidate),
    }


def build_v62_hype_alignment_profit_lock(
    aligned_market: pd.DataFrame,
    *,
    config: HypeExitReplayConfig,
    fold_count: int = 5,
) -> V62HypeProfitLockReview:
    """Compare the unchanged aligned exit with the exact A60 lock."""
    if isinstance(fold_count, bool) or not isinstance(fold_count, int):
        raise ValueError("V62 HYPE fold_count must be an integer")
    if fold_count < 2:
        raise ValueError("V62 HYPE fold_count must be at least two")
    control_policy = HypeExitPolicy(_CONTROL_ID)
    candidate_policy = HypeExitPolicy(
        _CANDIDATE_ID,
        profit_activation_bps=60.0,
        profit_floor_bps=15.0,
        trailing_giveback_bps=30.0,
    )
    control = develop_hype_exit_policy(
        aligned_market, control_policy, config, fold_count
    )
    candidate = develop_hype_exit_policy(
        aligned_market, candidate_policy, config, fold_count
    )
    tests = _promotion_tests(control, candidate, fold_count)
    report = _report(config, control, candidate, tests)
    return V62HypeProfitLockReview(
        report,
        _trade_rows((control, candidate)),
    )


def _promotion_tests(
    control: HypePolicyDevelopment,
    candidate: HypePolicyDevelopment,
    fold_count: int,
) -> dict[str, bool]:
    summary = _summary(candidate)
    sides = summary["side_summary"]
    if not isinstance(sides, dict):
        raise RuntimeError("V62 HYPE side summary is invalid")
    minimum_positive_folds = math.ceil(fold_count * 0.6)
    return {
        "net_improves_control": (
            candidate.report.net_return_bps > control.report.net_return_bps
        ),
        "profit_factor_above_one": _profit_factor_above_one(candidate),
        "positive_without_largest_winner": (
            float(summary["net_excluding_largest_winner_bps"]) > 0.0
        ),
        "chronological_fold_support": (
            candidate.positive_folds >= minimum_positive_folds
        ),
        "both_sides_positive": all(
            float(_side_record(sides, side)["net_return_bps"]) > 0.0
            for side in ("long", "short")
        ),
        "minimum_completed_lifecycles": candidate.report.completed_trades >= 30,
    }


def _report(
    config: HypeExitReplayConfig,
    control: HypePolicyDevelopment,
    candidate: HypePolicyDevelopment,
    tests: dict[str, bool],
) -> dict[str, object]:
    passed = all(tests.values())
    return {
        "schema_version": 1,
        "mode": "v62_hype_alignment_profit_lock_research_only_v1",
        "execution_authority": "none",
        "automatic_promotion": False,
        "trial_aborted": False,
        "candidate_policy": asdict(candidate.policy),
        "execution_contract": asdict(config),
        "control": _summary(control),
        "candidate": _summary(candidate),
        "recommendation_tests": tests,
        "disposition": (
            "eligible_for_separate_operator_review"
            if passed
            else "reject_in_development"
        ),
        "live_change_approved": False,
        "limitations": [
            "the A60 hypothesis followed inspection of two current-profile lifecycles",
            "completed one-minute bars cannot reconstruct intrabar event ordering",
            "a passing review would still require exact local depth and tape validation",
            "this result cannot route, size, close, retain, or submit an order",
        ],
    }


def _summary(result: HypePolicyDevelopment) -> dict[str, object]:
    trades = result.report.trades
    values = tuple(trade.net_return_bps for trade in trades)
    winners = tuple(value for value in values if value > 0.0)
    return {
        "completed_trades": result.report.completed_trades,
        "wins": result.report.wins,
        "losses": result.report.losses,
        "net_return_bps": result.report.net_return_bps,
        "profit_factor": result.report.profit_factor,
        "maximum_drawdown_bps": result.report.maximum_drawdown_bps,
        "net_excluding_largest_winner_bps": sum(values) - max(winners, default=0.0),
        "chronological_fold_net_bps": list(result.fold_net_bps),
        "positive_folds": result.positive_folds,
        "side_summary": {
            side: _side_summary(result, side) for side in ("long", "short")
        },
        "exit_reasons": result.report.exit_reasons,
        "occupied_signals": result.report.occupied_signals,
    }


def _side_summary(
    result: HypePolicyDevelopment,
    side: str,
) -> dict[str, float | int]:
    values = tuple(
        trade.net_return_bps for trade in result.report.trades if trade.side == side
    )
    return {
        "completed_trades": len(values),
        "wins": sum(value > 0.0 for value in values),
        "losses": sum(value < 0.0 for value in values),
        "net_return_bps": sum(values),
    }


def _trade_rows(results: tuple[HypePolicyDevelopment, ...]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"policy_id": result.policy.policy_id, **asdict(trade)}
            for result in results
            for trade in result.report.trades
        ]
    )


def _profit_factor_above_one(result: HypePolicyDevelopment) -> bool:
    value = result.report.profit_factor
    return value is not None and value > 1.0


def _side_record(
    sides: dict[str, object],
    side: str,
) -> dict[str, float | int]:
    value = sides.get(side)
    if not isinstance(value, dict):
        raise RuntimeError(f"V62 HYPE {side} summary is invalid")
    return value
