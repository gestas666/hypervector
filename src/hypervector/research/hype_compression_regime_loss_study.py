"""Single-policy HYPE compression regime-loss exit study."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
)
from hypervector.research.hype_breakout_exit_replay import replay_hype_breakout_exits
from hypervector.research.hype_compression_exit_challenger import _filter_market
from hypervector.research.hype_compression_regime_loss_exit import (
    FixedRegimeLossComparison,
    combine_fixed_regime_loss_comparisons,
    compare_fixed_regime_loss_exits,
)

_LOSS_THRESHOLD_BPS = 20.0
_PERSISTENCE_DECISIONS = 5
_CONTROL_POLICY = HypeExitPolicy("compression_live_exit_control")


@dataclass(frozen=True)
class HypeCompressionRegimeLossStudy:
    """Development and later paired exits with no execution authority."""

    report: dict[str, object]
    development_trades: pd.DataFrame
    confirmation_trades: pd.DataFrame


def build_hype_compression_regime_loss_study(
    development: pd.DataFrame,
    confirmation_segments: tuple[pd.DataFrame, ...],
    *,
    frozen_compression_policy_id: str,
    config: HypeExitReplayConfig,
    fold_count: int,
) -> HypeCompressionRegimeLossStudy:
    """Evaluate one transferred exit on fixed exact compression lifecycles."""
    filtered, _ = _filter_market(development, frozen_compression_policy_id)
    control = replay_hype_breakout_exits(filtered, _CONTROL_POLICY, config)
    development_comparison = compare_fixed_regime_loss_exits(
        filtered,
        control.trades,
        config,
        loss_threshold_bps=_LOSS_THRESHOLD_BPS,
        persistence_decisions=_PERSISTENCE_DECISIONS,
        fold_count=fold_count,
    )
    later, unresolved = _later_comparison(
        confirmation_segments,
        frozen_compression_policy_id,
        config,
    )
    report = _study_report(
        frozen_compression_policy_id,
        development_comparison,
        later,
        unresolved,
    )
    return HypeCompressionRegimeLossStudy(
        report,
        development_comparison.trade_rows,
        later.trade_rows,
    )


def _later_comparison(
    segments: tuple[pd.DataFrame, ...],
    compression_policy_id: str,
    config: HypeExitReplayConfig,
) -> tuple[FixedRegimeLossComparison, int]:
    if not segments:
        raise ValueError("HYPE regime-loss study requires confirmation segments")
    comparisons: list[FixedRegimeLossComparison] = []
    unresolved = 0
    for segment_number, segment in enumerate(segments, start=1):
        filtered, _ = _filter_market(segment, compression_policy_id)
        replay = replay_hype_breakout_exits(filtered, _CONTROL_POLICY, config)
        controls = tuple(
            trade for trade in replay.trades if trade.exit_reason != "end_of_data"
        )
        unresolved += len(replay.trades) - len(controls)
        if not controls:
            continue
        comparison = compare_fixed_regime_loss_exits(
            filtered,
            controls,
            config,
            loss_threshold_bps=_LOSS_THRESHOLD_BPS,
            persistence_decisions=_PERSISTENCE_DECISIONS,
            fold_count=1,
        )
        comparison.trade_rows.insert(0, "segment", segment_number)
        comparisons.append(comparison)
    return (
        combine_fixed_regime_loss_comparisons(
            comparisons,
            loss_threshold_bps=_LOSS_THRESHOLD_BPS,
            persistence_decisions=_PERSISTENCE_DECISIONS,
            fold_count=1,
        ),
        unresolved,
    )


def _study_report(
    compression_policy_id: str,
    development: FixedRegimeLossComparison,
    later: FixedRegimeLossComparison,
    unresolved: int,
) -> dict[str, object]:
    development_acceptance = _development_acceptance(development.report)
    later_acceptance = _later_acceptance(later.report, unresolved)
    passed = bool(development_acceptance["passed"]) and bool(later_acceptance["passed"])
    return {
        "schema_version": 1,
        "mode": "hype_compression_regime_loss_exit_report_only",
        "execution_authority": "none",
        "frozen_compression_policy_id": compression_policy_id,
        "policy_id": "opp5_loss20",
        "trial_count": 1,
        "capital_reallocation_modeled": False,
        "development": development.report,
        "development_acceptance": development_acceptance,
        "later_confirmation": {
            **later.report,
            "selection_performed": False,
            "unresolved_lifecycles": unresolved,
        },
        "later_acceptance": later_acceptance,
        "disposition": (
            "requires_new_forward_evidence" if passed else "reject_transferred_exit"
        ),
        "limitations": _limitations(),
    }


def _development_acceptance(report: dict[str, object]) -> dict[str, object]:
    candidate = _mapping(report["candidate"])
    actual = _mapping(report["actual"])
    folds = [float(value) for value in report["fold_candidate_minus_actual_net_bps"]]
    checks = {
        "candidate_positive": float(candidate["net_return_bps"]) > 0.0,
        "candidate_positive_without_largest_winner": (
            float(candidate["without_largest_winner_net_bps"]) > 0.0
        ),
        "candidate_outperforms_actual": (
            float(report["candidate_minus_actual_net_bps"]) > 0.0
        ),
        "candidate_profit_factor_above_one": (
            float(candidate["profit_factor"] or 0.0) > 1.0
        ),
        "drawdown_not_worse": (
            float(candidate["maximum_drawdown_bps"])
            <= float(actual["maximum_drawdown_bps"])
        ),
        "majority_positive_delta_folds": sum(value > 0.0 for value in folds)
        >= len(folds) // 2 + 1,
    }
    return {"passed": all(checks.values()), "checks": checks}


def _later_acceptance(report: dict[str, object], unresolved: int) -> dict[str, object]:
    candidate = _mapping(report["candidate"])
    checks = {
        "complete_lifecycle_evidence": unresolved == 0,
        "candidate_positive": float(candidate["net_return_bps"]) > 0.0,
        "candidate_positive_without_largest_winner": (
            float(candidate["without_largest_winner_net_bps"]) > 0.0
        ),
        "candidate_outperforms_actual": (
            float(report["candidate_minus_actual_net_bps"]) > 0.0
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("HYPE regime-loss comparison summary must be a mapping")
    return value


def _limitations() -> list[str]:
    return [
        "opp5_loss20 was transferred unchanged from prior broad HYPE research",
        "entries are fixed so earlier exits receive no additional capital reuse",
        "later confirmation was already opened and cannot select or retune the rule",
        "one-minute OHLC cannot prove private-order queue position",
        "the report cannot place, close, resize, gate, or promote a live trade",
    ]
