"""Full-archive bidirectional candidate families for exact ``xyz:MU``."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import Literal

import pandas as pd

from hypervector.data.oxa_api import validate_market_symbol
from hypervector.research.hip3_archive_inputs import (
    ArchivePartitionName as PartitionName,
    ArchiveSignalBuilder as SignalBuilder,
    ArchiveSignalConfig as SignalConfig,
    archive_family_builder as _family_builder,
    build_archive_breakout_signals as _breakout_builder,
    build_archive_swing_signals as _swing_builder,
    canonical_archive_windows,
    partition_evaluation_end as _partition_evaluation_end,
    validate_archive_bars as _validate_bars,
    validate_archive_cadence as _validate_cadence,
    validate_archive_windows as _validate_windows,
    validate_development_only_partitions as _validate_partition_names,
)
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.mu_hip3_candidate import (
    MU_SYMBOL,
    MuChronologicalWindows,
    MuPartitionResult,
    chronological_windows,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)
from hypervector.research.swing_ha_signals import SwingHaSignalConfig

_INITIAL_EQUITY_USD = 500.0
_MAXIMUM_HOLD_SECONDS = 86_400


@dataclass(frozen=True)
class MuArchiveExecution:
    """Fee, notional, leverage, and latency contract for archive replay."""

    effective_taker_fee_rate: float
    notional_usd: float
    venue_max_leverage: float
    nominal_latency_bps_per_side: float
    stress_latency_bps_per_side: float
    stress_visible_tail_bps_per_side: float
    fixed_stop_bps: float = 80.0
    maximum_hold_bars: int = 96
    risk_high_column: str = "high"
    risk_low_column: str = "low"
    entry_risk_high_column: str | None = None
    entry_risk_low_column: str | None = None
    symbol: str = MU_SYMBOL

    def __post_init__(self) -> None:
        """Reject aliasing or invalid execution assumptions."""
        validate_market_symbol(self.symbol, "hip3")
        positive = (
            self.effective_taker_fee_rate,
            self.notional_usd,
            self.venue_max_leverage,
            self.fixed_stop_bps,
        )
        if any(not isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("MU fee, notional, and leverage must be positive")
        costs = (
            self.nominal_latency_bps_per_side,
            self.stress_latency_bps_per_side,
            self.stress_visible_tail_bps_per_side,
        )
        if any(not isfinite(value) or value < 0.0 for value in costs):
            raise ValueError("MU latency and tail costs must be non-negative")
        if self.stress_latency_bps_per_side < self.nominal_latency_bps_per_side:
            raise ValueError("MU stress latency cannot be below nominal latency")
        if (
            isinstance(self.maximum_hold_bars, bool)
            or not isinstance(self.maximum_hold_bars, int)
            or self.maximum_hold_bars <= 0
        ):
            raise ValueError("MU maximum hold bars must be a positive integer")
        if not self.risk_high_column.strip() or not self.risk_low_column.strip():
            raise ValueError("MU risk-path columns must be non-empty")
        if (self.entry_risk_high_column is None) != (
            self.entry_risk_low_column is None
        ):
            raise ValueError("MU entry risk-path columns must be paired")
        if self.entry_risk_high_column is not None and (
            not self.entry_risk_high_column.strip()
            or not self.entry_risk_low_column
            or not self.entry_risk_low_column.strip()
        ):
            raise ValueError("MU entry risk-path columns must be non-empty")


@dataclass(frozen=True)
class MuArchiveTrial:
    """One complete development-only trial for one candidate family."""

    config: SignalConfig
    development: SharedPortfolioReport
    folds: tuple[SharedPortfolioReport, ...]


@dataclass(frozen=True)
class MuArchiveFamilyResult:
    """Selected family recipe and untouched chronological evidence."""

    family: str
    proposed_provider_id: str
    proposed_profile_id: str
    trials: tuple[MuArchiveTrial, ...]
    selected_config: SignalConfig
    partitions: tuple[MuPartitionResult, ...]


@dataclass(frozen=True)
class MuArchiveCandidateResult:
    """Complete two-family report-only qualification result."""

    symbol: str
    timeframe: str
    windows: MuChronologicalWindows
    families: tuple[MuArchiveFamilyResult, ...]
    execution_authority: str = "none"
    automatic_promotion: bool = False


@dataclass(frozen=True)
class MuArchiveTrack:
    """One immutable family/timeframe identity selected on development only."""

    timeframe: str
    family: str
    provider_id: str
    profile_id: str
    config: SignalConfig
    symbol: str = MU_SYMBOL


def select_mu_archive_trial(
    trials: tuple[MuArchiveTrial, ...],
) -> MuArchiveTrial:
    """Select fold-stable profitability before side breadth or trade count."""
    if not trials:
        raise ValueError("MU archive trial selection requires evidence")
    return max(trials, key=_selection_key)


def select_mu_development_track(
    results: tuple[MuArchiveCandidateResult, ...],
) -> MuArchiveTrack:
    """Select at most one track using development trials and folds only."""
    candidates = [
        (select_mu_archive_trial(family.trials), result, family)
        for result in results
        for family in result.families
    ]
    if not candidates:
        raise ValueError("MU development track selection requires candidates")
    if len({result.symbol for result in results}) != 1:
        raise ValueError("HIP-3 development tracks require one exact symbol")
    if any(result.windows != results[0].windows for result in results[1:]):
        raise ValueError("MU cross-timeframe selection requires identical UTC windows")
    trial, result, family = max(candidates, key=lambda value: _selection_key(value[0]))
    return MuArchiveTrack(
        result.timeframe,
        family.family,
        family.proposed_provider_id,
        family.proposed_profile_id,
        trial.config,
        result.symbol,
    )


def mu_archive_portfolio_config(
    execution: MuArchiveExecution,
    *,
    family: str,
    stress: bool,
) -> SharedPortfolioConfig:
    """Return the exact-quote 80 bps stop and 24-hour replay contract."""
    if family not in {"swing_ha", "breakout_pressure"}:
        raise ValueError(f"unsupported MU archive family: {family}")
    leverage = min(5.0, execution.venue_max_leverage)
    latency = (
        execution.stress_latency_bps_per_side
        if stress
        else (execution.nominal_latency_bps_per_side)
    )
    slippage = latency + (execution.stress_visible_tail_bps_per_side if stress else 0.0)
    fee = execution.effective_taker_fee_rate
    return SharedPortfolioConfig(
        symbol=execution.symbol,
        initial_equity=_INITIAL_EQUITY_USD,
        margin_fraction=execution.notional_usd / (_INITIAL_EQUITY_USD * leverage),
        leverage=leverage,
        venue_max_leverage=execution.venue_max_leverage,
        stop_margin_pct=execution.fixed_stop_bps * leverage / 100.0,
        maximum_stop_distance_bps=execution.fixed_stop_bps,
        entry_fee_rate=fee,
        target_fee_rate=fee,
        market_exit_fee_rate=fee,
        liquidation_fee_rate=fee,
        entry_slippage_bps=slippage,
        market_exit_slippage_bps=slippage,
        max_hold_bars=execution.maximum_hold_bars,
        max_hold_seconds=_MAXIMUM_HOLD_SECONDS,
        reentry_cooldown_bars=1,
        same_direction_reentry_requires_reset=family == "breakout_pressure",
        open_bid_column="entry_bid",
        open_ask_column="entry_ask",
        close_bid_column="decision_bid",
        close_ask_column="decision_ask",
        risk_high_column=execution.risk_high_column,
        risk_low_column=execution.risk_low_column,
        entry_risk_high_column=execution.entry_risk_high_column,
        entry_risk_low_column=execution.entry_risk_low_column,
    )


def evaluate_hip3_archive_candidates(
    bars: pd.DataFrame,
    execution: MuArchiveExecution,
    *,
    timeframe: str = "15m",
    partition_names: tuple[PartitionName, ...] = ("development",),
    windows: MuChronologicalWindows | None = None,
    swing_configs: tuple[SwingHaSignalConfig, ...],
    breakout_configs: tuple[Hip3BreakoutPressureConfig, ...],
) -> MuArchiveCandidateResult:
    """Tune two exact HIP-3 families using development evidence only."""
    _validate_bars(bars)
    validate_market_symbol(execution.symbol, "hip3")
    if timeframe not in {"5m", "15m"}:
        raise ValueError("MU archive replay timeframe must be 5m or 15m")
    _validate_cadence(bars, timeframe, execution.maximum_hold_bars)
    _validate_partition_names(partition_names)
    asset_slug = execution.symbol.split(":", maxsplit=1)[1].lower()
    identity_suffix = "_15m" if timeframe == "15m" else "_5m"
    windows = windows or chronological_windows(bars.index)
    _validate_windows(bars, windows, timeframe)
    swing = _evaluate_family(
        bars,
        execution,
        windows,
        "swing_ha",
        f"hip3_{asset_slug}_full_l2_swing_ha_bidirectional{identity_suffix}_v1",
        f"{asset_slug}_full_l2_swing_ha_bidirectional{identity_suffix}_research_v1",
        tuple(swing_configs),
        _swing_builder,
        timeframe,
        partition_names,
    )
    breakout = _evaluate_family(
        bars,
        execution,
        windows,
        "breakout_pressure",
        f"hip3_{asset_slug}_full_l2_breakout_pressure_bidirectional{identity_suffix}_v1",
        f"{asset_slug}_full_l2_breakout_pressure_bidirectional{identity_suffix}_research_v1",
        tuple(breakout_configs),
        _breakout_builder,
        timeframe,
        partition_names,
    )
    return MuArchiveCandidateResult(
        execution.symbol, timeframe, windows, (swing, breakout)
    )


def evaluate_mu_archive_candidates(
    bars: pd.DataFrame,
    execution: MuArchiveExecution,
    *,
    timeframe: str = "15m",
    partition_names: tuple[PartitionName, ...] = ("development",),
    windows: MuChronologicalWindows | None = None,
    swing_configs: tuple[SwingHaSignalConfig, ...],
    breakout_configs: tuple[Hip3BreakoutPressureConfig, ...],
) -> MuArchiveCandidateResult:
    """Preserve the exact-MU entry point for existing qualification jobs."""
    if execution.symbol != MU_SYMBOL:
        raise ValueError("MU archive replay requires exact xyz:MU identity")
    return evaluate_hip3_archive_candidates(
        bars,
        execution,
        timeframe=timeframe,
        partition_names=partition_names,
        windows=windows,
        swing_configs=swing_configs,
        breakout_configs=breakout_configs,
    )


def _evaluate_family(
    bars: pd.DataFrame,
    execution: MuArchiveExecution,
    windows: MuChronologicalWindows,
    family: str,
    provider_id: str,
    profile_id: str,
    configs: tuple[SignalConfig, ...],
    builder: SignalBuilder,
    timeframe: str,
    partition_names: tuple[PartitionName, ...],
) -> MuArchiveFamilyResult:
    if not configs or len(set(configs)) != len(configs):
        raise ValueError(f"{family} configs must be non-empty and unique")
    evaluation_end = _partition_evaluation_end(windows, partition_names[-1])
    causal_bars = bars.loc[bars.index < evaluation_end].copy()
    signals = {config: builder(causal_bars, config, timeframe) for config in configs}
    trials = tuple(
        _development_trial(
            causal_bars, signals[config], config, windows, execution, family
        )
        for config in configs
    )
    selected = select_mu_archive_trial(trials).config
    partitions = _partition_results(
        causal_bars,
        signals[selected],
        windows,
        execution,
        family,
        partition_names,
    )
    return MuArchiveFamilyResult(
        family, provider_id, profile_id, trials, selected, partitions
    )


def _development_trial(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    config: SignalConfig,
    windows: MuChronologicalWindows,
    execution: MuArchiveExecution,
    family: str,
) -> MuArchiveTrial:
    development = _window_report(
        bars,
        signals,
        windows.development_start_utc,
        windows.development_end_utc,
        execution,
        family,
        False,
    )
    folds = tuple(
        _window_report(bars, signals, start, end, execution, family, False)
        for start, end in windows.development_folds
    )
    return MuArchiveTrial(config, development, folds)


def _partition_results(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    windows: MuChronologicalWindows,
    execution: MuArchiveExecution,
    family: str,
    partition_names: tuple[PartitionName, ...],
) -> tuple[MuPartitionResult, ...]:
    all_bounds = (
        ("development", windows.development_start_utc, windows.development_end_utc),
        ("validation", windows.development_end_utc, windows.validation_end_utc),
        ("holdout", windows.validation_end_utc, windows.holdout_end_utc),
    )
    bounds = tuple(item for item in all_bounds if item[0] in partition_names)
    return tuple(
        MuPartitionResult(
            name,
            start,
            end,
            _window_report(bars, signals, start, end, execution, family, False),
            _window_report(bars, signals, start, end, execution, family, True),
        )
        for name, start, end in bounds
    )


def evaluate_mu_archive_track_partition(
    bars: pd.DataFrame,
    execution: MuArchiveExecution,
    windows: MuChronologicalWindows,
    track: MuArchiveTrack,
    partition_name: Literal["validation", "holdout"],
) -> MuPartitionResult:
    """Evaluate one frozen track on one next chronological partition only."""
    if execution.symbol != track.symbol:
        raise ValueError("frozen HIP-3 track and execution symbols must match")
    _validate_bars(bars)
    _validate_cadence(bars, track.timeframe, execution.maximum_hold_bars)
    _validate_windows(bars, windows, track.timeframe)
    bounds = {
        "validation": (windows.development_end_utc, windows.validation_end_utc),
        "holdout": (windows.validation_end_utc, windows.holdout_end_utc),
    }
    if partition_name not in bounds:
        raise ValueError("frozen MU partition must be validation or holdout")
    start, end = bounds[partition_name]
    causal_bars = bars.loc[bars.index < end].copy()
    builder = _family_builder(track.family)
    signals = builder(causal_bars, track.config, track.timeframe)
    return MuPartitionResult(
        partition_name,
        start,
        end,
        _window_report(
            causal_bars, signals, start, end, execution, track.family, False
        ),
        _window_report(causal_bars, signals, start, end, execution, track.family, True),
    )


def attach_mu_track_partitions(
    results: tuple[MuArchiveCandidateResult, ...],
    track: MuArchiveTrack,
    partitions: tuple[MuPartitionResult, ...],
) -> tuple[MuArchiveCandidateResult, ...]:
    """Attach frozen out-of-sample evidence to exactly one selected track."""
    attached = 0
    output: list[MuArchiveCandidateResult] = []
    for result in results:
        families: list[MuArchiveFamilyResult] = []
        for family in result.families:
            matched = (
                result.symbol == track.symbol
                and result.timeframe == track.timeframe
                and family.proposed_provider_id == track.provider_id
            )
            families.append(
                replace(family, partitions=(*family.partitions, *partitions))
                if matched
                else family
            )
            attached += int(matched)
        output.append(replace(result, families=tuple(families)))
    if attached != 1:
        raise ValueError("frozen MU track must match exactly one candidate family")
    return tuple(output)


def _window_report(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    execution: MuArchiveExecution,
    family: str,
    stress: bool,
) -> SharedPortfolioReport:
    selected = bars.index.to_series().ge(start) & bars.index.to_series().lt(end)
    return evaluate_shared_bar_portfolio(
        bars.loc[selected].copy(),
        signals.loc[selected].copy(),
        mu_archive_portfolio_config(execution, family=family, stress=stress),
    )


def _selection_key(trial: MuArchiveTrial) -> tuple[float, ...]:
    direction_net = _direction_net(trial.development)
    fold_sides = [
        value for report in trial.folds for value in _direction_net(report).values()
    ]
    return (
        float(sum(report.net_pnl_usd > 0.0 for report in trial.folds)),
        min((report.net_pnl_usd for report in trial.folds), default=0.0),
        float(sum(value > 0.0 for value in fold_sides)),
        min(fold_sides, default=0.0),
        float(sum(value > 0.0 for value in direction_net.values())),
        min(direction_net.values()),
        trial.development.net_pnl_usd,
        -abs(trial.development.maximum_drawdown_pct),
        float(trial.development.completed_trades),
    )


def _direction_net(report: SharedPortfolioReport) -> dict[str, float]:
    return {
        direction: sum(
            trade.net_pnl_usd for trade in report.trades if trade.direction == direction
        )
        for direction in ("long", "short")
    }


canonical_mu_archive_windows = canonical_archive_windows
select_hip3_development_track = select_mu_development_track
evaluate_hip3_archive_track_partition = evaluate_mu_archive_track_partition
attach_hip3_track_partitions = attach_mu_track_partitions
