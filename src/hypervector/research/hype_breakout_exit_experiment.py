"""Frozen chronological experiment for HYPE breakout-specific exits."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
from statistics import median

import pandas as pd

from hypervector.research.hype_breakout_exit_replay import (
    HypeExitPolicy,
    HypeExitReplayConfig,
    HypeExitReplayReport,
    replay_hype_breakout_exits,
)


@dataclass(frozen=True)
class HypePolicyDevelopment:
    """One policy's development result and chronological fold attribution."""

    policy: HypeExitPolicy
    report: HypeExitReplayReport
    fold_net_bps: tuple[float, ...]

    @property
    def positive_folds(self) -> int:
        """Count folds with strictly positive post-cost returns."""
        return sum(value > 0.0 for value in self.fold_net_bps)

    @property
    def median_fold_net_bps(self) -> float:
        """Return the median chronological fold result."""
        return float(median(self.fold_net_bps))


def declared_hype_exit_policies() -> tuple[HypeExitPolicy, ...]:
    """Return the frozen control and three strategy-specific challengers."""
    return (
        HypeExitPolicy("generic_8h_control"),
        HypeExitPolicy("breakout_invalidation_8h", exit_on_invalidation=True),
        HypeExitPolicy("structural_reversal_8h", exit_on_reversal=True),
        HypeExitPolicy(
            "invalidation_or_reversal_8h",
            exit_on_invalidation=True,
            exit_on_reversal=True,
        ),
    )


def select_hype_exit_policy(
    results: tuple[HypePolicyDevelopment, ...],
) -> HypePolicyDevelopment:
    """Select by fold stability, then return, PF, drawdown, and stable identity."""
    if not results:
        raise ValueError("HYPE exit selection requires challenger results")
    identities = [result.policy.policy_id for result in results]
    if len(set(identities)) != len(identities):
        raise ValueError("HYPE exit selection policy identities must be unique")
    ordered = sorted(results, key=lambda result: result.policy.policy_id)
    return max(ordered, key=_selection_score)


def run_hype_exit_experiment(
    market: pd.DataFrame,
    *,
    config: HypeExitReplayConfig | None = None,
    holdout_days: int = 60,
    fold_count: int = 5,
) -> dict[str, object]:
    """Select on purged development data and open one final holdout once."""
    cfg = config or HypeExitReplayConfig()
    development, holdout, split = split_hype_exit_market(market, cfg, holdout_days)
    policies = declared_hype_exit_policies()
    developed = tuple(
        develop_hype_exit_policy(development, policy, cfg, fold_count)
        for policy in policies
    )
    selected = select_hype_exit_policy(developed[1:])
    holdout_reports = _holdout_reports(holdout, policies[0], selected.policy, cfg)
    sensitivity = _friction_sensitivity(holdout, policies[0], selected.policy, cfg)
    return _artifact(
        market,
        split,
        cfg,
        developed,
        selected,
        holdout_reports,
        sensitivity,
    )


def build_hype_live_extension_comparison(
    market: pd.DataFrame,
    *,
    holdout_days: int = 60,
) -> dict[str, object]:
    """Compare fixed 8h and exact live 8h-to-24h exit mechanics report-only."""
    fixed = HypeExitReplayConfig()
    live = HypeExitReplayConfig(
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_minutes=1_440,
    )
    development, holdout, split = split_hype_exit_market(
        market,
        live,
        holdout_days,
    )
    development_reports = _extension_period_reports(development, fixed, live)
    holdout_reports = _extension_period_reports(holdout, fixed, live)
    return {
        "schema_version": 1,
        "mode": "hype_live_extension_parity_report_only",
        "execution_authority": "none",
        "contract": _extension_contract(fixed, live),
        "split": split,
        "trial_accounting": {"current_policy_trials": 4},
        "development": development_reports,
        "holdout_already_opened": holdout_reports,
        "development_comparison": _extension_delta(development_reports),
        "holdout_comparison": _extension_delta(holdout_reports),
        "limitations": _extension_limitations(),
    }


def build_hype_momentum_exit_comparison(
    market: pd.DataFrame,
    *,
    holdout_days: int = 60,
) -> dict[str, object]:
    """Compare the live timer with one completed-5m momentum exit report-only."""
    live = HypeExitReplayConfig(
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_minutes=1_440,
    )
    development, holdout, split = split_hype_exit_market(
        market,
        live,
        holdout_days,
    )
    development_reports = _momentum_period_reports(development, live)
    holdout_reports = _momentum_period_reports(holdout, live)
    return {
        "schema_version": 1,
        "mode": "hype_5m_momentum_exit_report_only",
        "execution_authority": "none",
        "contract": _momentum_contract(live),
        "split": split,
        "trial_accounting": {"predeclared_exit_arms": 2},
        "development": development_reports,
        "holdout_already_opened": holdout_reports,
        "development_comparison": _momentum_delta(development_reports),
        "holdout_comparison": _momentum_delta(holdout_reports),
        "limitations": _momentum_limitations(),
    }


def _momentum_period_reports(
    market: pd.DataFrame,
    config: HypeExitReplayConfig,
) -> dict[str, dict[str, object]]:
    control = HypeExitPolicy("live_extension_8h_to_24h")
    challenger = HypeExitPolicy(
        "five_minute_momentum_reversal",
        exit_on_5m_rsi_reversal=True,
    )
    return {
        control.policy_id: _extension_report(market, control, config),
        challenger.policy_id: _extension_report(market, challenger, config),
    }


def _momentum_delta(values: dict[str, dict[str, object]]) -> dict[str, float]:
    control = values["live_extension_8h_to_24h"]
    challenger = values["five_minute_momentum_reversal"]
    return {
        "momentum_minus_live_net_bps": float(challenger["net_return_bps"])
        - float(control["net_return_bps"]),
        "momentum_minus_live_drawdown_bps": float(challenger["maximum_drawdown_bps"])
        - float(control["maximum_drawdown_bps"]),
    }


def _momentum_contract(config: HypeExitReplayConfig) -> dict[str, object]:
    return {
        "report_only": True,
        "performance_gate": False,
        "automatic_promotion": False,
        "same_signal_stream": True,
        "decision": "fresh completed-5m RSI14 cross of EMA7 against position",
        "fill": "next 1m open with adverse slippage",
        "venue_stop_precedence": True,
        "execution": asdict(config),
    }


def _momentum_limitations() -> list[str]:
    return [
        "the final 60-day block was previously opened and is descriptive only",
        "one-minute bars cannot reproduce intrabar order or private queue state",
        "fixed slippage does not reproduce every live IOC fill",
        "different exit timing changes which overlapping signals are occupied",
        "one predeclared challenger cannot establish a durable exit edge",
    ]


def build_breakout_entry_direction_comparison(
    structural_market: pd.DataFrame,
    breakout_market: pd.DataFrame,
    *,
    holdout_days: int = 60,
) -> dict[str, object]:
    """Compare hourly structural side with actual 5m breakout direction."""
    structural_market, breakout_market, entry_accounting = (
        _align_entry_direction_markets(structural_market, breakout_market)
    )
    config = HypeExitReplayConfig()
    structural_dev, structural_holdout, split = split_hype_exit_market(
        structural_market,
        config,
        holdout_days,
    )
    breakout_dev, breakout_holdout, breakout_split = split_hype_exit_market(
        breakout_market,
        config,
        holdout_days,
    )
    if split != breakout_split:
        raise ValueError("entry-direction comparison markets have different splits")
    development = _entry_direction_period_reports(
        structural_dev,
        breakout_dev,
        config,
    )
    holdout = _entry_direction_period_reports(
        structural_holdout,
        breakout_holdout,
        config,
    )
    return {
        "schema_version": 1,
        "mode": "cross_asset_breakout_entry_direction_report_only",
        "execution_authority": "none",
        "report_only": True,
        "contract": {
            "same_breakout_onsets": True,
            "thresholds_tuned": False,
            "automatic_promotion": False,
            "structural_side_source": "completed_1h_sma10_sma30_relation",
            "breakout_side_source": "completed_5m_breakout_direction",
            "execution": asdict(config),
        },
        "split": split,
        "entry_accounting": entry_accounting,
        "trial_accounting": {"predeclared_entry_arms": 2},
        "development": development,
        "holdout_already_opened": holdout,
        "development_comparison": _entry_direction_delta(development),
        "holdout_comparison": _entry_direction_delta(holdout),
        "limitations": [
            "the final 60-day block was already opened and is descriptive only",
            "one-minute bars cannot reproduce intrabar order or private queue state",
            "fixed slippage cannot reproduce every live IOC fill",
            "entry side changes lifecycle sequencing when signals overlap",
            "this single comparison does not establish a durable cross-asset edge",
        ],
    }


def _align_entry_direction_markets(
    structural: pd.DataFrame,
    breakout: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    if not structural.index.equals(breakout.index):
        raise ValueError("entry-direction comparison markets must share one index")
    structural_onsets = structural["entry_side"].notna()
    breakout_onsets = breakout["entry_side"].notna()
    common = structural_onsets & breakout_onsets
    if not common.any():
        raise ValueError("entry-direction comparison has no shared directional onset")
    aligned_structural = structural.copy()
    aligned_breakout = breakout.copy()
    aligned_structural.loc[~common, "entry_side"] = None
    aligned_breakout.loc[~common, "entry_side"] = None
    accounting = {
        "compared_onsets": int(common.sum()),
        "hourly_structural_only_onsets": int((structural_onsets & ~common).sum()),
        "breakout_direction_only_onsets": int((breakout_onsets & ~common).sum()),
    }
    return aligned_structural, aligned_breakout, accounting


def _entry_direction_period_reports(
    structural: pd.DataFrame,
    breakout: pd.DataFrame,
    config: HypeExitReplayConfig,
) -> dict[str, dict[str, object]]:
    policy = HypeExitPolicy("breakout_entry_direction_control")
    return {
        "hourly_structural_side": _extension_report(structural, policy, config),
        "breakout_continuation_side": _extension_report(breakout, policy, config),
    }


def _entry_direction_delta(values: dict[str, dict[str, object]]) -> dict[str, float]:
    structural = values["hourly_structural_side"]
    breakout = values["breakout_continuation_side"]
    return {
        "breakout_minus_structural_net_bps": float(breakout["net_return_bps"])
        - float(structural["net_return_bps"]),
        "breakout_minus_structural_drawdown_bps": float(
            breakout["maximum_drawdown_bps"]
        )
        - float(structural["maximum_drawdown_bps"]),
    }


def _extension_period_reports(
    market: pd.DataFrame,
    fixed: HypeExitReplayConfig,
    live: HypeExitReplayConfig,
) -> dict[str, dict[str, object]]:
    policy = HypeExitPolicy("hype_breakout_entry_control")
    return {
        "fixed_8h": _extension_report(market, policy, fixed),
        "live_extension_8h_to_24h": _extension_report(market, policy, live),
    }


def _extension_report(
    market: pd.DataFrame,
    policy: HypeExitPolicy,
    config: HypeExitReplayConfig,
) -> dict[str, object]:
    report = replay_hype_breakout_exits(market, policy, config)
    return {**_report_metrics(report), "exit_reasons": report.exit_reasons}


def _extension_delta(values: dict[str, dict[str, object]]) -> dict[str, float]:
    fixed = values["fixed_8h"]
    live = values["live_extension_8h_to_24h"]
    return {
        "live_minus_fixed_net_bps": float(live["net_return_bps"])
        - float(fixed["net_return_bps"]),
        "live_minus_fixed_drawdown_bps": float(live["maximum_drawdown_bps"])
        - float(fixed["maximum_drawdown_bps"]),
    }


def _extension_contract(
    fixed: HypeExitReplayConfig,
    live: HypeExitReplayConfig,
) -> dict[str, object]:
    return {
        "report_only": True,
        "performance_gate": False,
        "automatic_promotion": False,
        "same_signal_stream": True,
        "fixed": asdict(fixed),
        "live": asdict(live),
    }


def _extension_limitations() -> list[str]:
    return [
        "the final 60-day block was previously opened and is descriptive only",
        "one-minute bars cannot reproduce intrabar order or private queue state",
        "fixed slippage does not reproduce every live IOC fill",
        "different hold durations alter which overlapping signals are occupied",
        "mechanical parity does not establish a profitable entry edge",
    ]


def split_hype_exit_market(
    market: pd.DataFrame,
    config: HypeExitReplayConfig,
    holdout_days: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Return purged development and sealed final-block market slices."""
    if isinstance(holdout_days, bool) or holdout_days < 1:
        raise ValueError("HYPE exit holdout_days must be positive")
    end_exclusive = market.index[-1] + pd.Timedelta(minutes=1)
    holdout_start = end_exclusive - pd.Timedelta(days=holdout_days)
    purge_minutes = _maximum_lifecycle_minutes(config)
    development_end = holdout_start - pd.Timedelta(minutes=purge_minutes)
    development = market.loc[market.index < development_end]
    holdout = market.loc[market.index >= holdout_start]
    if len(development) < 2 or len(holdout) < 2:
        raise ValueError("HYPE exit market is too short for the requested split")
    split = {
        "development_start_utc": development.index[0].isoformat(),
        "development_end_exclusive_utc": development_end.isoformat(),
        "purge_minutes": purge_minutes,
        "holdout_start_utc": holdout_start.isoformat(),
        "holdout_end_exclusive_utc": end_exclusive.isoformat(),
        "development_rows": len(development),
        "holdout_rows": len(holdout),
    }
    return development, holdout, split


def _maximum_lifecycle_minutes(config: HypeExitReplayConfig) -> int:
    hard = config.hard_maximum_hold_minutes
    return hard if hard is not None else config.maximum_hold_minutes


def develop_hype_exit_policy(
    market: pd.DataFrame,
    policy: HypeExitPolicy,
    config: HypeExitReplayConfig,
    fold_count: int,
) -> HypePolicyDevelopment:
    """Replay one policy and attribute its trades to chronological folds."""
    if isinstance(fold_count, bool) or fold_count < 2:
        raise ValueError("HYPE exit fold_count must be at least two")
    report = replay_hype_breakout_exits(market, policy, config)
    boundaries = _fold_boundaries(market.index, fold_count)
    fold_net = [0.0] * fold_count
    for trade in report.trades:
        stamp = pd.Timestamp(trade.entry_time_utc)
        fold = min(
            int(boundaries.searchsorted(stamp, side="right") - 1), fold_count - 1
        )
        fold_net[max(fold, 0)] += trade.net_return_bps
    return HypePolicyDevelopment(policy, report, tuple(fold_net))


def _fold_boundaries(index: pd.DatetimeIndex, fold_count: int) -> pd.DatetimeIndex:
    start = index[0]
    end = index[-1] + pd.Timedelta(minutes=1)
    step = (end.value - start.value) // fold_count
    values = [start.value + step * position for position in range(fold_count)]
    values.append(end.value)
    return pd.to_datetime(values, utc=True)


def _selection_score(result: HypePolicyDevelopment) -> tuple[float, ...]:
    report = result.report
    profit_factor = _selection_profit_factor(report)
    return (
        float(result.positive_folds),
        result.median_fold_net_bps,
        report.net_return_bps,
        profit_factor,
        -report.maximum_drawdown_bps,
    )


def _selection_profit_factor(report: HypeExitReplayReport) -> float:
    if report.profit_factor is not None:
        return report.profit_factor
    if report.gross_profit_bps > 0.0 and report.gross_loss_bps == 0.0:
        return math.inf
    return 0.0


def _holdout_reports(
    market: pd.DataFrame,
    control: HypeExitPolicy,
    selected: HypeExitPolicy,
    config: HypeExitReplayConfig,
) -> dict[str, HypeExitReplayReport]:
    return {
        control.policy_id: replay_hype_breakout_exits(market, control, config),
        selected.policy_id: replay_hype_breakout_exits(market, selected, config),
    }


def _friction_sensitivity(
    market: pd.DataFrame,
    control: HypeExitPolicy,
    selected: HypeExitPolicy,
    config: HypeExitReplayConfig,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for fee_bps in (3.0, 4.5, 6.0):
        for slippage_bps in (0.0, 2.0, 5.0):
            trial = replace(
                config,
                fee_bps_per_side=fee_bps,
                slippage_bps_per_side=slippage_bps,
            )
            for policy in (control, selected):
                report = replay_hype_breakout_exits(market, policy, trial)
                rows.append(
                    {
                        "policy_id": policy.policy_id,
                        "fee_bps_per_side": fee_bps,
                        "slippage_bps_per_side": slippage_bps,
                        **_report_metrics(report),
                    }
                )
    return rows


def _artifact(
    market: pd.DataFrame,
    split: dict[str, object],
    config: HypeExitReplayConfig,
    developed: tuple[HypePolicyDevelopment, ...],
    selected: HypePolicyDevelopment,
    holdout: dict[str, HypeExitReplayReport],
    sensitivity: list[dict[str, object]],
) -> dict[str, object]:
    holdout_values = list(holdout.values())
    control, challenger = holdout_values[0], holdout_values[1]
    return {
        "schema_version": 1,
        "mode": "hype_breakout_exit_challenge_report_only",
        "execution_authority": "none",
        "contract": _contract(config),
        "market": {
            "start_utc": market.index[0].isoformat(),
            "end_utc": market.index[-1].isoformat(),
            "rows": len(market),
            "entry_signals": int(market["entry_side"].notna().sum()),
            "funding_events": int(market["funding_rate"].ne(0.0).sum()),
        },
        "split": split,
        "trial_accounting": {
            "development_policy_trials": len(developed),
            "holdout_policy_trials": len(holdout),
            "holdout_friction_trials": len(sensitivity),
            "total_trials": len(developed) + len(holdout) + len(sensitivity),
        },
        "development": {
            result.policy.policy_id: _development_summary(result)
            for result in developed
        },
        "selection": {
            "selected_challenger": selected.policy.policy_id,
            "rule": "positive_folds, median_fold_net, aggregate_net, profit_factor, lower_drawdown, lexical_id",
            "holdout_not_used_for_selection": True,
        },
        "holdout": {key: _report_summary(value) for key, value in holdout.items()},
        "holdout_comparison": _comparison(control, challenger),
        "holdout_friction_sensitivity": sensitivity,
        "limitations": _limitations(),
    }


def _contract(config: HypeExitReplayConfig) -> dict[str, object]:
    return {
        "entry": "completed_5m_BREAKOUT_transition_with_completed_1h_SMA10x30_direction",
        "entry_fill": "next_1m_open_with_adverse_slippage",
        "position_limit": "one_HYPE_position",
        "protective_stop_bps": config.stop_bps,
        "maximum_hold_minutes": config.maximum_hold_minutes,
        "maximum_hold_policy": config.maximum_hold_policy,
        "hard_maximum_hold_minutes": config.hard_maximum_hold_minutes,
        "maximum_hold_role": "emergency_backstop_common_to_all_policies",
        "fee_bps_per_side": config.fee_bps_per_side,
        "slippage_bps_per_side": config.slippage_bps_per_side,
        "funding": "actual_Hyperliquid_hourly_event_rates",
    }


def _development_summary(result: HypePolicyDevelopment) -> dict[str, object]:
    return {
        "policy": asdict(result.policy),
        "metrics": _report_metrics(result.report),
        "fold_net_bps": list(result.fold_net_bps),
        "positive_folds": result.positive_folds,
        "median_fold_net_bps": result.median_fold_net_bps,
    }


def _report_summary(report: HypeExitReplayReport) -> dict[str, object]:
    return {
        "metrics": _report_metrics(report),
        "exit_reasons": report.exit_reasons,
        "monthly_net_bps": report.monthly_net_bps,
    }


def _report_metrics(report: HypeExitReplayReport) -> dict[str, object]:
    return {
        "completed_trades": report.completed_trades,
        "wins": report.wins,
        "losses": report.losses,
        "net_return_bps": report.net_return_bps,
        "profit_factor": report.profit_factor,
        "maximum_drawdown_bps": report.maximum_drawdown_bps,
        "total_fee_bps": report.total_fee_bps,
        "funding_bps": report.funding_bps,
        "occupied_signals": report.occupied_signals,
    }


def _comparison(
    control: HypeExitReplayReport,
    challenger: HypeExitReplayReport,
) -> dict[str, object]:
    return {
        "control_policy_id": control.policy_id,
        "challenger_policy_id": challenger.policy_id,
        "challenger_minus_control_net_bps": (
            challenger.net_return_bps - control.net_return_bps
        ),
        "challenger_minus_control_drawdown_bps": (
            challenger.maximum_drawdown_bps - control.maximum_drawdown_bps
        ),
        "observed_outcome": _comparison_label(control, challenger),
    }


def _comparison_label(
    control: HypeExitReplayReport,
    challenger: HypeExitReplayReport,
) -> str:
    if challenger.net_return_bps <= control.net_return_bps:
        return "challenger_did_not_outperform_control"
    if challenger.net_return_bps <= 0.0:
        return "challenger_less_negative_but_not_profitable"
    return "challenger_positive_and_outperformed_control"


def _limitations() -> list[str]:
    return [
        "one-minute OHLC cannot reconstruct within-bar path ordering beyond conservative stop handling",
        "market entries and exits use fixed slippage rather than depth and queue replay",
        "the final 60-day block is a single temporal sample, not proof of future edge",
        "live polling, HTTP latency, venue rejection, and stop-placement latency are not replayed",
        "results test the current entry source and do not validate the regime detector independently",
    ]
