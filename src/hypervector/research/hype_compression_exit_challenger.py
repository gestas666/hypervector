"""Report-only exit-policy study for the frozen HYPE compression entries."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from hypervector.research.hype_breakout_entry_features import (
    build_hype_entry_features,
)
from hypervector.research.hype_breakout_exit_experiment import (
    HypePolicyDevelopment,
    develop_hype_exit_policy,
    select_hype_exit_policy,
)
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
    HypeExitTrade,
)
from hypervector.research.hype_breakout_exit_replay import replay_hype_breakout_exits
from hypervector.research.hype_compression_breakout_challenger import (
    HypeCompressionEvidence,
    apply_hype_compression_policy,
    declared_hype_compression_policies,
)


@dataclass(frozen=True)
class HypeCompressionExitStudy:
    """Development selection and confirmation rows without execution authority."""

    report: dict[str, object]
    development_trades: pd.DataFrame
    confirmation_trades: pd.DataFrame


def declared_hype_compression_exit_policies() -> tuple[HypeExitPolicy, ...]:
    """Return the unchanged exit plus three previously declared reset-aware locks."""
    return (
        HypeExitPolicy("compression_live_exit_control"),
        _reset_policy("compression_a25_reset", 25.0, 15.0, 10.0),
        _reset_policy("compression_a40_reset", 40.0, 15.0, 20.0),
        _reset_policy("compression_a60_reset", 60.0, 15.0, 30.0),
    )


def build_hype_compression_exit_study(
    development: pd.DataFrame,
    confirmation_segments: tuple[pd.DataFrame, ...],
    *,
    frozen_compression_policy_id: str,
    config: HypeExitReplayConfig | None = None,
    fold_count: int = 5,
) -> HypeCompressionExitStudy:
    """Select an exit on development and score only that identity later."""
    cfg = config or HypeExitReplayConfig()
    filtered, evidence = _filter_market(
        development,
        frozen_compression_policy_id,
    )
    developed = tuple(
        develop_hype_exit_policy(filtered, policy, cfg, fold_count)
        for policy in declared_hype_compression_exit_policies()
    )
    selected = select_hype_exit_policy(developed[1:])
    later, confirmation_rows = _later_confirmation(
        confirmation_segments,
        frozen_compression_policy_id,
        developed[0].policy,
        selected.policy,
        cfg,
    )
    return HypeCompressionExitStudy(
        _study_report(
            frozen_compression_policy_id,
            evidence,
            developed,
            selected,
            later,
            cfg,
        ),
        _development_rows(developed),
        confirmation_rows,
    )


def _reset_policy(
    policy_id: str,
    activation_bps: float,
    floor_bps: float,
    giveback_bps: float,
) -> HypeExitPolicy:
    return HypeExitPolicy(
        policy_id,
        profit_activation_bps=activation_bps,
        profit_floor_bps=floor_bps,
        trailing_giveback_bps=giveback_bps,
        reentry_requires_structural_reset=True,
    )


def _filter_market(
    market: pd.DataFrame,
    policy_id: str,
) -> tuple[pd.DataFrame, HypeCompressionEvidence]:
    matches = [
        policy
        for policy in declared_hype_compression_policies()
        if policy.policy_id == policy_id
        and policy.maximum_5m_bbwp_percentile is not None
    ]
    if len(matches) != 1:
        raise ValueError("frozen HYPE compression exit policy is not a challenger")
    features = build_hype_entry_features(market)
    return apply_hype_compression_policy(market, features, matches[0])


def _later_confirmation(
    segments: tuple[pd.DataFrame, ...],
    compression_id: str,
    control: HypeExitPolicy,
    selected: HypeExitPolicy,
    config: HypeExitReplayConfig,
) -> tuple[dict[str, object], pd.DataFrame]:
    if not segments:
        raise ValueError("HYPE compression exit confirmation requires segments")
    summaries: dict[str, object] = {}
    rows: list[dict[str, object]] = []
    for policy in (control, selected):
        trades, policy_rows = _confirmation_policy(
            segments,
            compression_id,
            policy,
            config,
        )
        summaries[policy.policy_id] = _trade_metrics(trades)
        rows.extend(policy_rows)
    return {
        "selection_performed": False,
        "policies": summaries,
        "selected_exit_policy_id": selected.policy_id,
        "comparison": _later_comparison(
            summaries, control.policy_id, selected.policy_id
        ),
    }, pd.DataFrame(rows)


def _confirmation_policy(
    segments: tuple[pd.DataFrame, ...],
    compression_id: str,
    policy: HypeExitPolicy,
    config: HypeExitReplayConfig,
) -> tuple[list[HypeExitTrade], list[dict[str, object]]]:
    resolved: list[HypeExitTrade] = []
    rows: list[dict[str, object]] = []
    for number, segment in enumerate(segments, start=1):
        filtered, _ = _filter_market(segment, compression_id)
        replay = replay_hype_breakout_exits(filtered, policy, config)
        for trade in replay.trades:
            censored = trade.exit_reason == "end_of_data"
            if not censored:
                resolved.append(trade)
            rows.append(
                {
                    "exit_policy_id": policy.policy_id,
                    "segment": number,
                    "censored": censored,
                    **asdict(trade),
                }
            )
    return resolved, rows


def _study_report(
    compression_id: str,
    evidence: HypeCompressionEvidence,
    developed: tuple[HypePolicyDevelopment, ...],
    selected: HypePolicyDevelopment,
    later: dict[str, object],
    config: HypeExitReplayConfig,
) -> dict[str, object]:
    development_acceptance = _development_acceptance(developed[0], selected)
    later_acceptance = _later_acceptance(later)
    accepted = bool(development_acceptance["passed"]) and bool(
        later_acceptance["passed"]
    )
    return {
        "schema_version": 1,
        "mode": "hype_compression_exit_challenger_report_only",
        "execution_authority": "none",
        "frozen_compression_policy_id": compression_id,
        "entry_signal_evidence": asdict(evidence),
        "execution_contract": asdict(config),
        "trial_accounting": {
            "prior_known_policy_trials": 40,
            "current_exit_policy_trials": len(developed),
            "cumulative_known_policy_trials": 40 + len(developed),
        },
        "development": {
            result.policy.policy_id: _development_summary(result)
            for result in developed
        },
        "development_selection": {
            "selected_exit_policy_id": selected.policy.policy_id,
            "holdout_used": False,
            "rule": "positive_folds_then_median_then_net_pf_drawdown",
        },
        "development_acceptance": development_acceptance,
        "later_confirmation": later,
        "later_acceptance": later_acceptance,
        "disposition": (
            "challenger_requires_new_forward_evidence"
            if accepted
            else "retain_control_exit"
        ),
        "limitations": [
            "exit policies were previously declared on a noisier entry population",
            "later confirmation was already opened and cannot select the exit",
            "one-minute OHLC cannot prove historical private-order execution",
            "positive aggregate PnL must survive largest-winner removal and folds",
        ],
    }


def _development_acceptance(
    control: HypePolicyDevelopment,
    selected: HypePolicyDevelopment,
) -> dict[str, object]:
    report = selected.report
    required_folds = len(selected.fold_net_bps) // 2 + 1
    checks = {
        "positive_net": report.net_return_bps > 0.0,
        "positive_without_largest_winner": _without_largest(list(report.trades)) > 0.0,
        "majority_positive_folds": selected.positive_folds >= required_folds,
        "profit_factor_above_one": (report.profit_factor or 0.0) > 1.0,
        "outperforms_control_net": report.net_return_bps
        > control.report.net_return_bps,
        "drawdown_not_worse_than_control": (
            report.maximum_drawdown_bps <= control.report.maximum_drawdown_bps
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def _later_acceptance(later: dict[str, object]) -> dict[str, object]:
    comparison = _summary_mapping(later["comparison"])
    checks = {
        "positive_net": comparison["selected_positive"] is True,
        "positive_without_largest_winner": (
            comparison["selected_positive_without_largest_winner"] is True
        ),
        "outperforms_control_net": comparison["selected_outperformed_control"] is True,
    }
    return {"passed": all(checks.values()), "checks": checks}


def _development_summary(result: HypePolicyDevelopment) -> dict[str, object]:
    report = result.report
    trades = list(report.trades)
    return {
        "policy": asdict(result.policy),
        "completed_trades": report.completed_trades,
        "wins": report.wins,
        "losses": report.losses,
        "net_return_bps": report.net_return_bps,
        "profit_factor": report.profit_factor,
        "maximum_drawdown_bps": report.maximum_drawdown_bps,
        "without_largest_winner_net_bps": _without_largest(trades),
        "positive_folds": result.positive_folds,
        "median_fold_net_bps": result.median_fold_net_bps,
        "fold_net_bps": list(result.fold_net_bps),
        "exit_reasons": report.exit_reasons,
        "reset_blocked_signals": report.reset_blocked_signals,
    }


def _trade_metrics(trades: list[HypeExitTrade]) -> dict[str, object]:
    values = [trade.net_return_bps for trade in trades]
    profits = sum(value for value in values if value > 0.0)
    losses = -sum(value for value in values if value <= 0.0)
    return {
        "completed_trades": len(trades),
        "wins": sum(value > 0.0 for value in values),
        "losses": sum(value <= 0.0 for value in values),
        "net_return_bps": sum(values),
        "profit_factor": profits / losses if losses else None,
        "maximum_drawdown_bps": _maximum_drawdown(values),
        "without_largest_winner_net_bps": _without_largest(trades),
    }


def _without_largest(trades: list[HypeExitTrade]) -> float:
    values = [trade.net_return_bps for trade in trades]
    largest = max((value for value in values if value > 0.0), default=0.0)
    return sum(values) - largest


def _maximum_drawdown(values: list[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _later_comparison(
    summaries: dict[str, object],
    control_id: str,
    selected_id: str,
) -> dict[str, object]:
    control = _summary_mapping(summaries[control_id])
    selected = _summary_mapping(summaries[selected_id])
    return {
        "selected_minus_control_net_bps": float(selected["net_return_bps"])
        - float(control["net_return_bps"]),
        "selected_positive": float(selected["net_return_bps"]) > 0.0,
        "selected_positive_without_largest_winner": float(
            selected["without_largest_winner_net_bps"]
        )
        > 0.0,
        "selected_outperformed_control": float(selected["net_return_bps"])
        > float(control["net_return_bps"]),
    }


def _summary_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError("HYPE compression exit summary is malformed")
    return value


def _development_rows(
    developed: tuple[HypePolicyDevelopment, ...],
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"exit_policy_id": result.policy.policy_id, **asdict(trade)}
            for result in developed
            for trade in result.report.trades
        ]
    )
