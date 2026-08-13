"""Evaluation and transparent ranking for ETH/SOL low-timeframe trials."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, replace
import math

import pandas as pd

from hypervector.research.low_tf_asset_tuning_models import (
    DevelopmentTrialSummary,
    LowTfAssetTrial,
    TrendEntryShape,
    TuningScenario,
    TuningTrialResult,
    default_entry_shapes,
    default_exit_shapes,
)
from hypervector.research.low_tf_asset_tuning_signals import (
    build_tuned_trend_signals,
)
from hypervector.research.low_tf_multi_asset_features import LowTfFeatureConfig
from hypervector.research.low_tf_multi_asset_replay import evaluate_low_tf_replay
from hypervector.research.low_tf_multi_asset_replay_models import LowTfReplayConfig
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig

_DEVELOPMENT_DAYS = 184.0


def declared_tuning_trials() -> tuple[LowTfAssetTrial, ...]:
    """Return the frozen ETH/SOL, long/short, entry/exit trial matrix."""
    return tuple(
        LowTfAssetTrial(symbol, side, entry, exit_shape)
        for symbol in ("ETH", "SOL")
        for side in ("long", "short")
        for entry in default_entry_shapes()
        for exit_shape in default_exit_shapes()
    )


def feature_config_for_entry(entry: TrendEntryShape) -> LowTfFeatureConfig:
    """Translate one tuning entry shape into the causal feature builder."""
    return LowTfFeatureConfig(
        breakout_lookback=entry.breakout_lookback,
        ema_fast=entry.ema_fast,
        ema_slow=entry.ema_slow,
    )


def evaluate_tuning_trial(
    *,
    minute_bars: pd.DataFrame,
    features: pd.DataFrame,
    trial: LowTfAssetTrial,
    segment: str,
    scenario: TuningScenario,
    venue_max_leverage: float,
) -> TuningTrialResult:
    """Replay one runtime-mappable trial through a one-minute venue path."""
    signals = build_tuned_trend_signals(
        features,
        symbol=trial.symbol,
        side=trial.side,
        entry_shape=trial.entry,
        exit_shape=trial.exit,
    )
    if signals.empty:
        return _empty_result(trial, segment, scenario, minute_bars)
    report = evaluate_low_tf_replay(
        minute_bars,
        features,
        signals,
        _replay_config(scenario, venue_max_leverage),
    )
    return TuningTrialResult(
        trial.trial_id,
        trial.symbol,
        trial.side,
        segment,
        scenario.name,
        len(signals),
        report.completed_trades,
        report.wins,
        report.losses,
        report.net_pnl_usd,
        report.profit_factor,
        report.maximum_drawdown_pct,
        report.total_fees_usd,
        report.funding_cashflow_usd,
        report.liquidations,
        len(report.rejections),
        _monthly_net(minute_bars, report.trades),
        tuple(asdict(trade) for trade in report.trades),
    )


def screen_tuning_trial(
    *,
    bars: pd.DataFrame,
    features: pd.DataFrame,
    trial: LowTfAssetTrial,
    segment: str,
    scenario: TuningScenario,
    venue_max_leverage: float,
) -> TuningTrialResult:
    """Broad-screen one trial on causal 5m bars before minute-path replay."""
    signals = build_tuned_trend_signals(
        features,
        symbol=trial.symbol,
        side=trial.side,
        entry_shape=trial.entry,
        exit_shape=trial.exit,
    )
    aligned = _screen_signal_frame(bars, features, signals, trial)
    report = evaluate_shared_bar_portfolio(
        bars,
        aligned,
        _screen_config(trial, scenario, venue_max_leverage),
    )
    return TuningTrialResult(
        trial.trial_id,
        trial.symbol,
        trial.side,
        segment,
        scenario.name,
        len(signals),
        report.completed_trades,
        report.wins,
        report.losses,
        report.net_pnl_usd,
        report.profit_factor,
        report.maximum_drawdown_pct,
        report.total_fees_usd,
        report.funding_cashflow_usd,
        report.liquidations,
        report.conflicting_entry_signals,
        tuple(sorted(report.monthly_net_pnl_usd.items())),
        tuple(asdict(trade) for trade in report.trades),
    )


def _screen_signal_frame(
    bars: pd.DataFrame,
    features: pd.DataFrame,
    signals: pd.DataFrame,
    trial: LowTfAssetTrial,
) -> pd.DataFrame:
    feature_times = pd.DatetimeIndex(features["bar_open_at"])
    if len(bars) != len(features) or not bars.index.equals(feature_times):
        raise ValueError("screen bars and features must be exactly aligned")
    aligned = pd.DataFrame(
        False,
        index=bars.index,
        columns=("long_entry", "short_entry", "long_exit", "short_exit"),
    )
    positions = signals["decision_position"].to_numpy(dtype=int)
    column = "long_entry" if trial.side == "long" else "short_entry"
    aligned.iloc[positions, aligned.columns.get_loc(column)] = True
    aligned["long_signal_name"] = trial.trial_id
    aligned["short_signal_name"] = trial.trial_id
    return aligned


def _screen_config(
    trial: LowTfAssetTrial,
    scenario: TuningScenario,
    venue_max_leverage: float,
) -> SharedPortfolioConfig:
    leverage = 5.0
    price_stop_fraction = trial.exit.stop_bps / 10_000.0
    margin_fraction = min(0.70, 0.005 / (price_stop_fraction * leverage))
    residual = scenario.round_trip_cost_bps - 9.0
    if residual < 0.0:
        raise ValueError("tuning friction cannot be below the 9 bps fee contract")
    return SharedPortfolioConfig(
        symbol=trial.symbol,
        initial_equity=15_000.0,
        margin_fraction=margin_fraction,
        leverage=leverage,
        venue_max_leverage=venue_max_leverage,
        target_margin_pct=(
            price_stop_fraction * trial.exit.target_r_multiple * leverage * 100.0
        ),
        stop_margin_pct=price_stop_fraction * leverage * 100.0,
        entry_fee_rate=0.00045,
        target_fee_rate=0.00045,
        market_exit_fee_rate=0.00045,
        liquidation_fee_rate=0.00045,
        entry_slippage_bps=residual / 2.0,
        market_exit_slippage_bps=residual / 2.0,
        max_hold_bars=trial.exit.maximum_hold_bars,
        reentry_cooldown_bars=1,
    )


def _replay_config(
    scenario: TuningScenario, venue_max_leverage: float
) -> LowTfReplayConfig:
    return LowTfReplayConfig(
        initial_equity=15_000.0,
        risk_fraction=0.005,
        maximum_margin_fraction=0.70,
        leverage=5.0,
        venue_max_leverage=venue_max_leverage,
        round_trip_cost_bps=scenario.round_trip_cost_bps,
        fee_round_trip_bps=9.0,
        liquidation_penalty_rate=0.01,
        reentry_cooldown_bars=1,
    )


def _empty_result(
    trial: LowTfAssetTrial,
    segment: str,
    scenario: TuningScenario,
    minute_bars: pd.DataFrame,
) -> TuningTrialResult:
    return TuningTrialResult(
        trial.trial_id,
        trial.symbol,
        trial.side,
        segment,
        scenario.name,
        0,
        0,
        0,
        0,
        0.0,
        None,
        0.0,
        0.0,
        0.0,
        0,
        0,
        _empty_months(minute_bars),
    )


def _monthly_net(
    minutes: pd.DataFrame, trades: tuple[object, ...]
) -> tuple[tuple[str, float], ...]:
    values = dict(_empty_months(minutes))
    for trade in trades:
        month = pd.Timestamp(getattr(trade, "exit_time_utc")).strftime("%Y-%m")
        values[month] = values.get(month, 0.0) + float(getattr(trade, "net_pnl_usd"))
    return tuple(sorted(values.items()))


def _empty_months(minutes: pd.DataFrame) -> tuple[tuple[str, float], ...]:
    if "timestamp" not in minutes or minutes.empty:
        raise ValueError("tuning replay requires timestamped minute bars")
    times = pd.DatetimeIndex(minutes["timestamp"])
    if times.tz is None:
        raise ValueError("tuning minute timestamps must be timezone-aware")
    periods = pd.period_range(
        times.min().tz_localize(None), times.max().tz_localize(None), freq="M"
    )
    return tuple((str(period), 0.0) for period in periods)


def summarize_development_results(
    trials: tuple[LowTfAssetTrial, ...],
    results: tuple[TuningTrialResult, ...],
) -> tuple[DevelopmentTrialSummary, ...]:
    """Rank complete nominal development results within each asset and side."""
    by_id = _validated_matrix(trials, results)
    groups: dict[tuple[str, str], list[DevelopmentTrialSummary]] = defaultdict(list)
    for trial in trials:
        result = by_id[trial.trial_id]
        groups[(trial.symbol, trial.side)].append(_summary(result))
    ranked: list[DevelopmentTrialSummary] = []
    for key in sorted(groups):
        ordered = sorted(groups[key], key=_rank_key)
        ranked.extend(
            replace(summary, rank=rank) for rank, summary in enumerate(ordered, start=1)
        )
    return tuple(ranked)


def select_development_trials(
    trials: tuple[LowTfAssetTrial, ...],
    summaries: tuple[DevelopmentTrialSummary, ...],
    *,
    per_group: int,
) -> tuple[LowTfAssetTrial, ...]:
    """Select a bounded development-only rank slice for each asset and side."""
    if isinstance(per_group, bool) or not isinstance(per_group, int) or per_group < 1:
        raise ValueError("selected trials per group must be a positive integer")
    by_id = {trial.trial_id: trial for trial in trials}
    if not by_id or len(by_id) != len(trials):
        raise ValueError("selection trials must be non-empty and unique")
    selected = tuple(
        by_id[summary.trial_id] for summary in summaries if summary.rank <= per_group
    )
    group_counts: dict[tuple[str, str], int] = defaultdict(int)
    for trial in trials:
        group_counts[(trial.symbol, trial.side)] += 1
    expected = sum(min(per_group, count) for count in group_counts.values())
    if len(selected) != expected or len({trial.trial_id for trial in selected}) != len(
        selected
    ):
        raise ValueError("development summaries do not form complete asset-side ranks")
    return selected


def order_trial_results(
    trials: tuple[LowTfAssetTrial, ...],
    results: tuple[TuningTrialResult, ...],
) -> tuple[TuningTrialResult, ...]:
    """Restore parallel results to the frozen declared-trial order."""
    indexed: dict[str, TuningTrialResult] = {}
    for result in results:
        if result.trial_id in indexed:
            raise ValueError(f"duplicate tuning result: {result.trial_id}")
        indexed[result.trial_id] = result
    declared = tuple(trial.trial_id for trial in trials)
    if set(indexed) != set(declared):
        raise ValueError("parallel tuning results do not cover declared trials")
    return tuple(indexed[trial_id] for trial_id in declared)


def _validated_matrix(
    trials: tuple[LowTfAssetTrial, ...],
    results: tuple[TuningTrialResult, ...],
) -> dict[str, TuningTrialResult]:
    identities = tuple(trial.trial_id for trial in trials)
    if not identities or len(set(identities)) != len(identities):
        raise ValueError("development tuning trials must be non-empty and unique")
    indexed: dict[str, TuningTrialResult] = {}
    for result in results:
        if result.trial_id in indexed:
            raise ValueError(f"duplicate development result: {result.trial_id}")
        if result.segment != "development" or result.scenario != "nominal":
            raise ValueError("development ranking requires nominal development results")
        indexed[result.trial_id] = result
    if set(indexed) != set(identities):
        raise ValueError("development results must cover every declared trial")
    for trial in trials:
        result = indexed[trial.trial_id]
        if (result.symbol, result.side) != (trial.symbol, trial.side):
            raise ValueError(f"development result identity mismatch: {trial.trial_id}")
    return indexed


def _summary(result: TuningTrialResult) -> DevelopmentTrialSummary:
    monthly = tuple(value for _, value in result.monthly_net_pnl_usd)
    return DevelopmentTrialSummary(
        trial_id=result.trial_id,
        symbol=result.symbol,
        side=result.side,
        rank=0,
        positive_months=sum(value > 0.0 for value in monthly),
        total_months=len(monthly),
        worst_month_usd=min(monthly, default=0.0),
        net_pnl_usd=result.net_pnl_usd,
        profit_factor=result.profit_factor,
        maximum_drawdown_pct=result.maximum_drawdown_pct,
        completed_trades=result.completed_trades,
        trades_per_30_days=result.completed_trades / (_DEVELOPMENT_DAYS / 30.0),
        liquidations=result.liquidations,
    )


def _rank_key(summary: DevelopmentTrialSummary) -> tuple[object, ...]:
    drawdown = max(summary.maximum_drawdown_pct, 1e-12)
    return_over_drawdown = summary.net_pnl_usd / drawdown
    profit_factor = summary.profit_factor
    factor_rank = (
        profit_factor
        if profit_factor is not None
        else (math.inf if summary.net_pnl_usd > 0.0 else 0.0)
    )
    return (
        summary.liquidations > 0,
        summary.net_pnl_usd <= 0.0,
        -summary.positive_months,
        -summary.worst_month_usd,
        -return_over_drawdown,
        -factor_rank,
        -summary.completed_trades,
        summary.trial_id,
    )
