"""Bounded development-only parameter trials for the four-Pine entry stack."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
from typing import Literal

import pandas as pd

from hypervector.research.pine_stack_adaptive_supertrend import (
    AdaptiveSupertrendConfig,
    build_adaptive_supertrend,
)
from hypervector.research.pine_stack_screen import PineStackScreenConfig
from hypervector.research.pine_stack_trend_levels import (
    TrendLevelsConfig,
    build_trend_levels,
)
from hypervector.research.pine_stack_tp_dimensions import (
    TpDimensionsConfig,
    build_tp_dimensions,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio

PineStackExitPolicy = Literal["cs_flip", "max_hold_only"]


@dataclass(frozen=True)
class PineStackTuningConfig:
    """One predeclared CS, structure, stop, and hold parameter identity."""

    cs_atr_period: int
    cs_sensitivity: float
    trend_lookback: int
    stop_margin_pct: float = 10.0
    maximum_hold_hours: int = 8
    tp_pivot_width: int = 3
    tp_bin_count: int = 5
    tp_minimum_directional_pool: int = 25
    tp_include_time_of_day: bool = True
    tp_exit_threshold: int | None = None
    exit_policy: PineStackExitPolicy = "cs_flip"

    def __post_init__(self) -> None:
        """Reject invalid or unbounded tuning parameters."""
        integers = (
            self.cs_atr_period,
            self.trend_lookback,
            self.maximum_hold_hours,
            self.tp_pivot_width,
            self.tp_bin_count,
            self.tp_minimum_directional_pool,
        )
        if any(isinstance(value, bool) or value < 1 for value in integers):
            raise ValueError("Pine tuning lengths and duration must be positive")
        numbers = (self.cs_sensitivity, self.stop_margin_pct)
        if any(not math.isfinite(value) or value <= 0.0 for value in numbers):
            raise ValueError("Pine tuning sensitivity and stop must be positive")
        if not isinstance(self.tp_include_time_of_day, bool):
            raise ValueError("Pine tuning TP time-of-day flag must be boolean")
        if self.tp_exit_threshold not in {None, 80, 100}:
            raise ValueError("Pine tuning TP threshold must be 80, 100, or disabled")
        if self.exit_policy not in {"cs_flip", "max_hold_only"}:
            raise ValueError("Pine tuning exit policy is unsupported")
        if self.exit_policy == "max_hold_only" and self.tp_exit_threshold is not None:
            raise ValueError("max-hold-only diagnostics cannot add a TP exit")

    @property
    def trial_id(self) -> str:
        """Return a stable human-readable parameter identity."""
        sensitivity = format(self.cs_sensitivity, "g").replace(".", "p")
        stop = format(self.stop_margin_pct, "g").replace(".", "p")
        base = (
            f"atr{self.cs_atr_period}_sens{sensitivity}"
            f"_trend{self.trend_lookback}_stop{stop}"
            f"_hold{self.maximum_hold_hours}h"
        )
        if self.tp_exit_threshold is None:
            return (
                f"{base}_maxhold_only" if self.exit_policy == "max_hold_only" else base
            )
        time_axis = int(self.tp_include_time_of_day)
        return (
            f"{base}_tp{self.tp_exit_threshold}_p{self.tp_pivot_width}"
            f"_b{self.tp_bin_count}_pool{self.tp_minimum_directional_pool}"
            f"_tod{time_axis}"
        )


@dataclass(frozen=True)
class PineStackTuningResult:
    """One independent friction-aware development tuning result."""

    config: PineStackTuningConfig
    symbol: str
    bar_minutes: int
    signal_count: int
    completed_trades: int
    wins: int
    losses: int
    net_pnl_usd: float
    profit_factor: float | None
    maximum_drawdown_pct: float
    total_fees_usd: float
    funding_cashflow_usd: float
    liquidations: int
    monthly_net_pnl_usd: dict[str, float]
    trade_records: tuple[dict[str, object], ...]
    execution_authority: str = "none"


@dataclass(frozen=True)
class PineStackTuningSummary:
    """Robustness-oriented rank for one complete development trial."""

    trial_id: str
    rank: int
    positive_neighbors: int
    evaluated_neighbors: int
    positive_months: int
    total_months: int
    worst_month_pnl_usd: float
    net_pnl_usd: float
    profit_factor: float | None
    maximum_drawdown_pct: float
    completed_trades: int
    liquidations: int


def declared_entry_parameter_grid() -> tuple[PineStackTuningConfig, ...]:
    """Return the frozen 27-cell CS/Trend development neighbor surface."""
    return tuple(
        PineStackTuningConfig(atr_period, sensitivity, trend_lookback)
        for atr_period in (7, 10, 14)
        for sensitivity in (3.0, 5.0, 8.0)
        for trend_lookback in (20, 30, 48)
    )


def declared_risk_parameter_grid() -> tuple[PineStackTuningConfig, ...]:
    """Return the frozen 9-cell stop/hold surface around the entry control."""
    return tuple(
        PineStackTuningConfig(
            cs_atr_period=10,
            cs_sensitivity=5.0,
            trend_lookback=30,
            stop_margin_pct=stop_margin_pct,
            maximum_hold_hours=maximum_hold_hours,
        )
        for stop_margin_pct in (5.0, 10.0, 15.0)
        for maximum_hold_hours in (4, 8, 16)
    )


def declared_tp_parameter_grid() -> tuple[PineStackTuningConfig, ...]:
    """Return the control and 8-cell TP-density support surface."""
    control = PineStackTuningConfig(10, 5.0, 30)
    challengers = tuple(
        PineStackTuningConfig(
            10,
            5.0,
            30,
            tp_pivot_width=pivot_width,
            tp_bin_count=bin_count,
            tp_minimum_directional_pool=minimum_pool,
            tp_exit_threshold=80,
        )
        for pivot_width in (3, 5)
        for bin_count in (5, 10)
        for minimum_pool in (25, 50)
    )
    return (control, *challengers)


def declared_tp_axis_threshold_grid() -> tuple[PineStackTuningConfig, ...]:
    """Return the control and four TP semantic challengers around the winner."""
    control = PineStackTuningConfig(10, 5.0, 30)
    challengers = tuple(
        PineStackTuningConfig(
            10,
            5.0,
            30,
            tp_pivot_width=5,
            tp_bin_count=5,
            tp_minimum_directional_pool=50,
            tp_include_time_of_day=include_time_of_day,
            tp_exit_threshold=threshold,
        )
        for include_time_of_day in (True, False)
        for threshold in (80, 100)
    )
    return (control, *challengers)


def declared_final_development_grid() -> tuple[PineStackTuningConfig, ...]:
    """Return the frozen 2x2 hold and simpler-TP interaction surface."""
    return tuple(
        PineStackTuningConfig(
            10,
            5.0,
            30,
            maximum_hold_hours=hold_hours,
            tp_pivot_width=5,
            tp_bin_count=5,
            tp_minimum_directional_pool=50,
            tp_include_time_of_day=False,
            tp_exit_threshold=threshold,
        )
        for hold_hours in (4, 8)
        for threshold in (None, 80)
    )


def declared_pseudo_holdout_grid() -> tuple[PineStackTuningConfig, ...]:
    """Return only the pre-frozen validation winner for pseudo-holdout."""
    return (PineStackTuningConfig(10, 5.0, 30),)


def declared_post_hoc_exit_grid() -> tuple[PineStackTuningConfig, ...]:
    """Return the failed control and one contaminated exit diagnostic."""
    return (
        PineStackTuningConfig(10, 5.0, 30),
        PineStackTuningConfig(10, 5.0, 30, exit_policy="max_hold_only"),
    )


def evaluate_pine_stack_tuning_trial(
    *,
    feature_bars: pd.DataFrame,
    scored_bars: pd.DataFrame,
    symbol: str,
    venue_max_leverage: float,
    bar_minutes: int,
    config: PineStackTuningConfig,
) -> PineStackTuningResult:
    """Evaluate one causal CS/Trend trial with shared economic assumptions."""
    adaptive, levels, dimensions = _build_components(feature_bars, bar_minutes, config)
    signals = _scored_signals(
        adaptive,
        levels,
        dimensions,
        scored_bars,
        symbol,
        config.tp_exit_threshold,
        config.exit_policy,
    )
    economics = PineStackScreenConfig(
        stop_margin_pct=config.stop_margin_pct,
        maximum_hold_hours=config.maximum_hold_hours,
    ).portfolio_config(
        symbol=symbol,
        bar_minutes=bar_minutes,
        venue_max_leverage=venue_max_leverage,
    )
    if config.exit_policy == "max_hold_only":
        economics = replace(economics, close_on_opposite_signal=False)
    market = scored_bars.set_index("bar_open_at").copy()
    report = evaluate_shared_bar_portfolio(market, signals, economics)
    return PineStackTuningResult(
        config,
        symbol,
        bar_minutes,
        int(signals[["long_entry", "short_entry"]].to_numpy().sum()),
        report.completed_trades,
        report.wins,
        report.losses,
        report.net_pnl_usd,
        report.profit_factor,
        abs(report.maximum_drawdown_pct),
        report.total_fees_usd,
        report.funding_cashflow_usd,
        report.liquidations,
        report.monthly_net_pnl_usd,
        tuple(asdict(trade) for trade in report.trades),
    )


def _build_components(
    feature_bars: pd.DataFrame,
    bar_minutes: int,
    config: PineStackTuningConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    adaptive = build_adaptive_supertrend(
        feature_bars,
        bar_minutes=bar_minutes,
        config=AdaptiveSupertrendConfig(
            atr_period=config.cs_atr_period,
            sensitivity=config.cs_sensitivity,
        ),
    )
    levels = build_trend_levels(
        feature_bars,
        bar_minutes=bar_minutes,
        config=TrendLevelsConfig(
            lookback=config.trend_lookback,
            ambiguity_policy="hold",
        ),
    )
    dimensions = (
        build_tp_dimensions(
            feature_bars,
            bar_minutes=bar_minutes,
            config=TpDimensionsConfig(
                pivot_width=config.tp_pivot_width,
                bin_count=config.tp_bin_count,
                include_time_of_day=config.tp_include_time_of_day,
                minimum_directional_pool=config.tp_minimum_directional_pool,
            ),
        )
        if config.tp_exit_threshold is not None
        else None
    )
    return adaptive, levels, dimensions


def rank_pine_stack_tuning_results(
    results: tuple[PineStackTuningResult, ...],
) -> tuple[PineStackTuningSummary, ...]:
    """Rank every result by local and temporal stability without filtering."""
    _validate_results(results)
    positive_ids = {
        result.config.trial_id for result in results if result.net_pnl_usd > 0.0
    }
    summaries = [_unranked_summary(result, results, positive_ids) for result in results]
    ordered = sorted(summaries, key=_ranking_key, reverse=True)
    return tuple(
        PineStackTuningSummary(**{**asdict(summary), "rank": rank})
        for rank, summary in enumerate(ordered, start=1)
    )


def _unranked_summary(
    result: PineStackTuningResult,
    results: tuple[PineStackTuningResult, ...],
    positive_ids: set[str],
) -> PineStackTuningSummary:
    neighbors = tuple(
        other for other in results if _direct_neighbor(result.config, other.config)
    )
    months = tuple(result.monthly_net_pnl_usd.values())
    return PineStackTuningSummary(
        trial_id=result.config.trial_id,
        rank=0,
        positive_neighbors=sum(
            other.config.trial_id in positive_ids for other in neighbors
        ),
        evaluated_neighbors=len(neighbors),
        positive_months=sum(value > 0.0 for value in months),
        total_months=len(months),
        worst_month_pnl_usd=min(months, default=0.0),
        net_pnl_usd=result.net_pnl_usd,
        profit_factor=result.profit_factor,
        maximum_drawdown_pct=result.maximum_drawdown_pct,
        completed_trades=result.completed_trades,
        liquidations=result.liquidations,
    )


def _ranking_key(summary: PineStackTuningSummary) -> tuple[float, ...]:
    profit_factor = summary.profit_factor or 0.0
    return (
        float(summary.positive_neighbors),
        float(summary.positive_months),
        summary.worst_month_pnl_usd,
        profit_factor,
        summary.net_pnl_usd,
        -summary.maximum_drawdown_pct,
    )


def _direct_neighbor(
    left: PineStackTuningConfig,
    right: PineStackTuningConfig,
) -> bool:
    dimensions = (
        ((7, 10, 14), left.cs_atr_period, right.cs_atr_period),
        ((3.0, 5.0, 8.0), left.cs_sensitivity, right.cs_sensitivity),
        ((20, 30, 48), left.trend_lookback, right.trend_lookback),
        ((5.0, 10.0, 15.0), left.stop_margin_pct, right.stop_margin_pct),
        ((4, 8, 16), left.maximum_hold_hours, right.maximum_hold_hours),
        ((3, 5), left.tp_pivot_width, right.tp_pivot_width),
        ((5, 10), left.tp_bin_count, right.tp_bin_count),
        (
            (25, 50),
            left.tp_minimum_directional_pool,
            right.tp_minimum_directional_pool,
        ),
        ((True, False), left.tp_include_time_of_day, right.tp_include_time_of_day),
        ((None, 80, 100), left.tp_exit_threshold, right.tp_exit_threshold),
        (("cs_flip", "max_hold_only"), left.exit_policy, right.exit_policy),
    )
    changes = 0
    for values, left_value, right_value in dimensions:
        if left_value == right_value:
            continue
        if left_value not in values or right_value not in values:
            return False
        if abs(values.index(left_value) - values.index(right_value)) != 1:
            return False
        changes += 1
    return changes == 1


def _validate_results(results: tuple[PineStackTuningResult, ...]) -> None:
    if not results:
        raise ValueError("Pine tuning ranking requires at least one result")
    identities = {result.config.trial_id for result in results}
    if len(identities) != len(results):
        raise ValueError("Pine tuning results contain duplicate trial identities")
    if any(result.execution_authority != "none" for result in results):
        raise ValueError("Pine tuning results must have no execution authority")


def _scored_signals(
    adaptive: pd.DataFrame,
    levels: pd.DataFrame,
    dimensions: pd.DataFrame | None,
    scored_bars: pd.DataFrame,
    symbol: str,
    tp_exit_threshold: int | None,
    exit_policy: PineStackExitPolicy,
) -> pd.DataFrame:
    scored_index = pd.DatetimeIndex(scored_bars["bar_open_at"])
    adaptive_index = pd.DatetimeIndex(adaptive["bar_open_at"])
    positions = adaptive_index.get_indexer(scored_index)
    if (positions < 0).any():
        raise ValueError("Pine tuning scored bars are absent from feature history")
    selected_adaptive = adaptive.iloc[positions].reset_index(drop=True)
    selected_levels = levels.iloc[positions].reset_index(drop=True)
    trend = selected_levels["trend_state"]
    long_entry = selected_adaptive["long_onset"] & trend.eq(1)
    short_entry = selected_adaptive["short_onset"] & trend.eq(-1)
    long_exit = selected_adaptive["short_onset"].astype(bool)
    short_exit = selected_adaptive["long_onset"].astype(bool)
    if exit_policy == "max_hold_only":
        long_exit &= False
        short_exit &= False
    if dimensions is not None and tp_exit_threshold is not None:
        selected_dimensions = dimensions.iloc[positions].reset_index(drop=True)
        density = selected_dimensions[f"density_{tp_exit_threshold}_onset"].astype(bool)
        long_exit |= density
        short_exit |= density
    return pd.DataFrame(
        {
            "long_entry": long_entry.to_numpy(dtype=bool),
            "short_entry": short_entry.to_numpy(dtype=bool),
            "long_exit": long_exit.to_numpy(dtype=bool),
            "short_exit": short_exit.to_numpy(dtype=bool),
            "signal_name": f"{symbol}:cs_trend_tuned",
            "execution_authority": "none",
        },
        index=scored_index,
    )
