"""Bounded post-hoc profit-protection research for HYPE breakout onsets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import median

import pandas as pd

from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
    HypeExitTrade,
)
from hypervector.research.hype_breakout_exit_experiment import (
    HypePolicyDevelopment,
    develop_hype_exit_policy,
    select_hype_exit_policy,
)


@dataclass(frozen=True)
class HypeProfitResearchBundle:
    """Summary plus exact baseline trade rows for reproducible analysis."""

    report: dict[str, object]
    trade_rows: pd.DataFrame


def declared_hype_profit_policies() -> tuple[HypeExitPolicy, ...]:
    """Return the predeclared control and profit-protection mechanisms."""
    return (
        HypeExitPolicy("generic_8h_control"),
        _profit_policy("profit_a25_floor15_trail10", 25.0, 10.0),
        _profit_policy("profit_a40_floor15_trail20", 40.0, 20.0),
        _profit_policy("profit_a60_floor15_trail30", 60.0, 30.0),
    )


def _profit_policy(
    policy_id: str,
    activation_bps: float,
    giveback_bps: float,
) -> HypeExitPolicy:
    return HypeExitPolicy(
        policy_id,
        profit_activation_bps=activation_bps,
        profit_floor_bps=15.0,
        trailing_giveback_bps=giveback_bps,
    )


def summarize_hype_excursions(
    trades: tuple[HypeExitTrade, ...],
) -> dict[str, object]:
    """Summarize realized favorable/adverse path headroom."""
    if not trades:
        raise ValueError("HYPE excursion research requires at least one trade")
    favorable = pd.Series(
        [trade.maximum_favorable_excursion_bps for trade in trades], dtype=float
    )
    adverse = pd.Series(
        [trade.maximum_adverse_excursion_bps for trade in trades], dtype=float
    )
    giveback = [
        trade.maximum_favorable_excursion_bps - trade.gross_return_bps
        for trade in trades
    ]
    return {
        "trades": len(trades),
        "mfe_bps_quantiles": _quantiles(favorable),
        "mae_bps_quantiles": _quantiles(adverse),
        "mfe_threshold_coverage": {
            f"{threshold:g}bps": float(favorable.ge(threshold).mean())
            for threshold in (15.0, 25.0, 40.0, 60.0, 80.0)
        },
        "median_favorable_giveback_bps": float(median(giveback)),
    }


def freeze_hype_entry_cohort(
    market: pd.DataFrame,
    control_trades: tuple[HypeExitTrade, ...],
) -> pd.DataFrame:
    """Retain only the exact signal timestamps admitted by the control."""
    if not control_trades:
        raise ValueError("HYPE fixed entry cohort requires control trades")
    if "entry_side" not in market:
        raise ValueError("HYPE fixed entry cohort requires entry_side")
    output = market.copy()
    output["entry_side"] = None
    observed: set[pd.Timestamp] = set()
    for trade in control_trades:
        timestamp = pd.Timestamp(trade.signal_time_utc)
        if timestamp in observed:
            raise ValueError("HYPE control signal timestamps must be unique")
        if timestamp not in market.index:
            raise ValueError("HYPE control signal timestamp is outside the market")
        if market.at[timestamp, "entry_side"] != trade.side:
            raise ValueError("HYPE control signal side does not match the market")
        output.at[timestamp, "entry_side"] = trade.side
        observed.add(timestamp)
    return output


def run_hype_profit_research(
    market: pd.DataFrame,
    *,
    config: HypeExitReplayConfig | None = None,
    fold_count: int = 5,
) -> dict[str, object]:
    """Run the counted post-hoc profit-protection mechanism screen."""
    return build_hype_profit_research_bundle(
        market,
        config=config,
        fold_count=fold_count,
    ).report


def build_hype_profit_research_bundle(
    market: pd.DataFrame,
    *,
    config: HypeExitReplayConfig | None = None,
    fold_count: int = 5,
) -> HypeProfitResearchBundle:
    """Return the summary and exact policy trade rows."""
    cfg = config or HypeExitReplayConfig()
    policies = declared_hype_profit_policies()
    developed = tuple(
        develop_hype_exit_policy(market, policy, cfg, fold_count) for policy in policies
    )
    selected = select_hype_exit_policy(developed[1:])
    fixed_market = freeze_hype_entry_cohort(market, developed[0].report.trades)
    matched = tuple(
        develop_hype_exit_policy(fixed_market, policy, cfg, fold_count)
        for policy in policies
    )
    matched_selected = select_hype_exit_policy(matched[1:])
    outperformed = _outperformed_control(developed[0], selected)
    report = _research_report(
        cfg,
        developed,
        selected,
        matched,
        matched_selected,
        outperformed,
    )
    return HypeProfitResearchBundle(report, _trade_rows(developed, matched))


def _research_report(
    config: HypeExitReplayConfig,
    developed: tuple[HypePolicyDevelopment, ...],
    selected: HypePolicyDevelopment,
    matched: tuple[HypePolicyDevelopment, ...],
    matched_selected: HypePolicyDevelopment,
    outperformed: bool,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "hype_breakout_profit_protection_post_hoc",
        "execution_authority": "none",
        "evidence_status": "post_hoc_exploration_only",
        "trial_accounting": {
            "prior_exit_trials": 24,
            "current_system_policy_trials": len(developed),
            "matched_entry_diagnostic_trials": len(matched),
            "cumulative_known_trials": 24 + len(developed) + len(matched),
        },
        "cost_contract": _cost_contract(config),
        "control_excursions": summarize_hype_excursions(developed[0].report.trades),
        "forward_candidate_excursions": summarize_hype_excursions(
            selected.report.trades
        ),
        "development": {
            result.policy.policy_id: _development_result(result) for result in developed
        },
        "matched_entry_diagnostic": {
            result.policy.policy_id: _development_result(result) for result in matched
        },
        "least_bad_challenger": {
            "policy_id": selected.policy.policy_id,
            "outperformed_control": outperformed,
        },
        "matched_entry_least_bad_challenger": {
            "policy_id": matched_selected.policy.policy_id,
            "diagnostic_only": True,
        },
        "forward_candidate": _forward_candidate(selected, outperformed),
        "limitations": _research_limitations(),
    }


def _forward_candidate(
    selected: HypePolicyDevelopment,
    outperformed: bool,
) -> dict[str, object]:
    return {
        "policy_id": selected.policy.policy_id if outperformed else None,
        "status": (
            "challenger_outperformed_control"
            if outperformed
            else "no_challenger_outperformed_control"
        ),
        "selection_basis": "development_fold_stability_only",
        "requires_fresh_forward_validation": True,
        "live_authority": False,
    }


def _trade_rows(
    developed: tuple[HypePolicyDevelopment, ...],
    matched: tuple[HypePolicyDevelopment, ...],
) -> pd.DataFrame:
    rows = [
        {
            "analysis_scope": scope,
            "policy_id": result.policy.policy_id,
            **asdict(trade),
        }
        for scope, results in (
            ("full_system", developed),
            ("matched_control_entries", matched),
        )
        for result in results
        for trade in result.report.trades
    ]
    if not rows:
        raise ValueError("HYPE profit research produced no trade rows")
    return pd.DataFrame(rows)


def _outperformed_control(
    control: HypePolicyDevelopment,
    challenger: HypePolicyDevelopment,
) -> bool:
    return (
        challenger.report.net_return_bps > control.report.net_return_bps
        and challenger.positive_folds >= control.positive_folds
    )


def _cost_contract(config: HypeExitReplayConfig) -> dict[str, float]:
    fee_round_trip = 2.0 * config.fee_bps_per_side
    slippage_round_trip = 2.0 * config.slippage_bps_per_side
    return {
        "fee_bps_per_side": config.fee_bps_per_side,
        "slippage_bps_per_side": config.slippage_bps_per_side,
        "modeled_round_trip_bps": fee_round_trip + slippage_round_trip,
        "profit_floor_bps": 15.0,
    }


def _development_result(result: HypePolicyDevelopment) -> dict[str, object]:
    report = result.report
    return {
        "policy": asdict(result.policy),
        "completed_trades": report.completed_trades,
        "wins": report.wins,
        "losses": report.losses,
        "net_return_bps": report.net_return_bps,
        "profit_factor": report.profit_factor,
        "maximum_drawdown_bps": report.maximum_drawdown_bps,
        "exit_reasons": report.exit_reasons,
        "fold_net_bps": list(result.fold_net_bps),
        "positive_folds": result.positive_folds,
        "median_fold_net_bps": result.median_fold_net_bps,
    }


def _research_limitations() -> list[str]:
    return [
        "the prior final 60-day block was already opened and is not reused as confirmation",
        "profit thresholds were defined after inspecting the earlier exit experiment",
        "completed one-minute bars cannot reconstruct within-bar activation ordering",
        "fresh forward venue evidence is required before any live implementation",
    ]


def _quantiles(values: pd.Series) -> dict[str, float]:
    return {
        f"p{int(quantile * 100):02d}": float(values.quantile(quantile))
        for quantile in (0.10, 0.25, 0.50, 0.75, 0.90, 0.95)
    }
