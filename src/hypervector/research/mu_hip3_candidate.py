"""Execution-incapable chronological qualification for the exact MU HIP-3 market."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd

from hypervector.research.hip3_swing_signals import (
    build_gap_aware_swing_ha_signals,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
    SharedPortfolioTrade,
)
from hypervector.research.swing_ha_signals import SwingHaSignalConfig

MU_SYMBOL = "xyz:MU"
MU_PROVIDER_ID = "hip3_mu_recent_candle_probe_swing_ha_bidirectional_v1"
MU_PROFILE_ID = "mu_recent_candle_probe_swing_ha_bidirectional_research_v1"
_NEW_YORK = ZoneInfo("America/New_York")
_INITIAL_EQUITY_USD = 500.0
_DEFAULT_LEVERAGE = 5.0


@dataclass(frozen=True)
class MuDepthFriction:
    """Measured MU depth/fee surface used by the causal simulator."""

    notional_usd: float
    effective_taker_fee_rate: float
    regular_round_trip_p90_bps: float
    regular_round_trip_p99_bps: float
    outside_round_trip_p90_bps: float
    outside_round_trip_p99_bps: float
    nominal_latency_bps_per_side: float
    stress_latency_bps_per_side: float
    venue_max_leverage: float = 10.0
    symbol: str = MU_SYMBOL

    def __post_init__(self) -> None:
        """Reject an aliased market or invalid economic evidence."""
        if self.symbol != MU_SYMBOL:
            raise ValueError("MU qualification requires exact xyz:MU identity")
        positive = (
            self.notional_usd,
            self.effective_taker_fee_rate,
            self.venue_max_leverage,
        )
        if any(not isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("MU notional, fee, and leverage must be positive")
        costs = (
            self.regular_round_trip_p90_bps,
            self.regular_round_trip_p99_bps,
            self.outside_round_trip_p90_bps,
            self.outside_round_trip_p99_bps,
            self.nominal_latency_bps_per_side,
            self.stress_latency_bps_per_side,
        )
        if any(not isfinite(value) or value < 0.0 for value in costs):
            raise ValueError("MU depth and latency costs must be non-negative")
        if self.regular_round_trip_p99_bps < self.regular_round_trip_p90_bps:
            raise ValueError("regular p99 cost must not be below p90")
        if self.outside_round_trip_p99_bps < self.outside_round_trip_p90_bps:
            raise ValueError("outside p99 cost must not be below p90")
        if self.stress_latency_bps_per_side < self.nominal_latency_bps_per_side:
            raise ValueError("MU stress latency must not be below nominal latency")


@dataclass(frozen=True)
class MuChronologicalWindows:
    """Non-overlapping development, validation, and final holdout bounds."""

    development_start_utc: pd.Timestamp
    development_end_utc: pd.Timestamp
    validation_end_utc: pd.Timestamp
    holdout_end_utc: pd.Timestamp
    development_folds: tuple[tuple[pd.Timestamp, pd.Timestamp], ...]


@dataclass(frozen=True)
class MuTrial:
    """One complete development-only parameter trial."""

    config: SwingHaSignalConfig
    development: SharedPortfolioReport
    folds: tuple[SharedPortfolioReport, ...]


@dataclass(frozen=True)
class MuPartitionResult:
    """One chronological partition under nominal and stress friction."""

    name: str
    start_utc: pd.Timestamp
    end_utc: pd.Timestamp
    nominal: SharedPortfolioReport
    stress: SharedPortfolioReport


@dataclass(frozen=True)
class MuCandidateResult:
    """Complete report-only MU candidate search and out-of-sample evidence."""

    symbol: str
    proposed_provider_id: str
    proposed_profile_id: str
    windows: MuChronologicalWindows
    trials: tuple[MuTrial, ...]
    selected_config: SwingHaSignalConfig
    partitions: tuple[MuPartitionResult, ...]
    execution_authority: str = "none"
    automatic_promotion: bool = False


@dataclass(frozen=True)
class TradeDiagnostics:
    """PnL robustness statistics for one trade subset."""

    trades: int
    wins: int
    losses: int
    breakeven: int
    net_pnl_usd: float
    profit_factor: float | None
    largest_winner_usd: float
    net_without_largest_winner_usd: float
    profit_factor_without_largest_winner: float | None


def chronological_windows(index: pd.DatetimeIndex) -> MuChronologicalWindows:
    """Split ordered bars by position into strict 60/20/20 chronology."""
    _validate_index(index)
    development_position = int(len(index) * 0.60)
    validation_position = int(len(index) * 0.80)
    if development_position < 6 or validation_position - development_position < 2:
        raise ValueError("MU chronology is too short for 60/20/20 evaluation")
    folds = _fold_bounds(index, development_position)
    cadence = index.to_series().diff().dropna().median()
    return MuChronologicalWindows(
        index[0],
        index[development_position],
        index[validation_position],
        index[-1] + cadence,
        folds,
    )


def quote_mu_bars(
    bars: pd.DataFrame,
    friction: MuDepthFriction,
    *,
    stress: bool,
) -> pd.DataFrame:
    """Add session-dependent executable bid/ask quotes from MU L2 evidence."""
    _validate_bars(bars)
    output = bars.copy()
    sessions = pd.Series(
        [_session_name(timestamp) for timestamp in output.index],
        index=output.index,
    )
    regular, outside, latency = _scenario_costs(friction, stress)
    cost_bps = sessions.map(
        {"us_regular_hours": regular, "outside_us_regular_hours": outside}
    ).astype(float)
    cost_rate = (cost_bps + latency) / 10_000.0
    output["friction_session"] = sessions
    output["open_bid"] = output["open"] * (1.0 - cost_rate)
    output["open_ask"] = output["open"] * (1.0 + cost_rate)
    output["close_bid"] = output["close"] * (1.0 - cost_rate)
    output["close_ask"] = output["close"] * (1.0 + cost_rate)
    return output


def evaluate_mu_swing_candidate(
    bars: pd.DataFrame,
    friction: MuDepthFriction,
    *,
    configs: tuple[SwingHaSignalConfig, ...],
) -> MuCandidateResult:
    """Select using development only, then evaluate validation and holdout."""
    _validate_bars(bars)
    if friction.symbol != MU_SYMBOL:
        raise ValueError("MU qualification requires exact xyz:MU identity")
    if not configs or len(set(configs)) != len(configs):
        raise ValueError("MU candidate configs must be non-empty and unique")
    windows = chronological_windows(bars.index)
    nominal = quote_mu_bars(bars, friction, stress=False)
    stress = quote_mu_bars(bars, friction, stress=True)
    signals = {
        config: build_gap_aware_swing_ha_signals(bars, config) for config in configs
    }
    trials = tuple(
        _development_trial(nominal, signals[config], config, windows, friction)
        for config in configs
    )
    selected = select_mu_trial(trials).config
    partitions = _partition_results(
        nominal, stress, signals[selected], windows, friction
    )
    return MuCandidateResult(
        MU_SYMBOL,
        MU_PROVIDER_ID,
        MU_PROFILE_ID,
        windows,
        trials,
        selected,
        partitions,
    )


def select_mu_trial(trials: tuple[MuTrial, ...]) -> MuTrial:
    """Select fold-stable profitability before side breadth or activity."""
    if not trials:
        raise ValueError("MU candidate selection requires trial evidence")
    return max(trials, key=_selection_key)


def summarize_trades(
    trades: Iterable[SharedPortfolioTrade],
) -> dict[str, TradeDiagnostics]:
    """Summarize all, directional, and U.S.-session trade subsets."""
    records = tuple(trades)
    subsets = {
        "all": records,
        "long": tuple(item for item in records if item.direction == "long"),
        "short": tuple(item for item in records if item.direction == "short"),
        "us_regular_hours": tuple(
            item for item in records if _trade_session(item) == "us_regular_hours"
        ),
        "outside_us_regular_hours": tuple(
            item
            for item in records
            if _trade_session(item) == "outside_us_regular_hours"
        ),
    }
    return {name: _trade_diagnostics(values) for name, values in subsets.items()}


def _development_trial(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    config: SwingHaSignalConfig,
    windows: MuChronologicalWindows,
    friction: MuDepthFriction,
) -> MuTrial:
    development = _window_report(
        bars,
        signals,
        windows.development_start_utc,
        windows.development_end_utc,
        friction,
    )
    folds = tuple(
        _window_report(bars, signals, start, end, friction)
        for start, end in windows.development_folds
    )
    return MuTrial(config, development, folds)


def _partition_results(
    nominal: pd.DataFrame,
    stress: pd.DataFrame,
    signals: pd.DataFrame,
    windows: MuChronologicalWindows,
    friction: MuDepthFriction,
) -> tuple[MuPartitionResult, ...]:
    bounds = (
        ("development", windows.development_start_utc, windows.development_end_utc),
        ("validation", windows.development_end_utc, windows.validation_end_utc),
        ("holdout", windows.validation_end_utc, windows.holdout_end_utc),
    )
    return tuple(
        MuPartitionResult(
            name,
            start,
            end,
            _window_report(nominal, signals, start, end, friction),
            _window_report(stress, signals, start, end, friction),
        )
        for name, start, end in bounds
    )


def _window_report(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    friction: MuDepthFriction,
) -> SharedPortfolioReport:
    selected = bars.index.to_series().ge(start) & bars.index.to_series().lt(end)
    return evaluate_shared_bar_portfolio(
        bars.loc[selected].copy(),
        signals.loc[selected].copy(),
        _portfolio_config(friction),
    )


def _portfolio_config(friction: MuDepthFriction) -> SharedPortfolioConfig:
    leverage = min(_DEFAULT_LEVERAGE, friction.venue_max_leverage)
    margin_fraction = friction.notional_usd / (_INITIAL_EQUITY_USD * leverage)
    fee = friction.effective_taker_fee_rate
    return SharedPortfolioConfig(
        symbol=MU_SYMBOL,
        initial_equity=_INITIAL_EQUITY_USD,
        margin_fraction=margin_fraction,
        leverage=leverage,
        venue_max_leverage=friction.venue_max_leverage,
        entry_fee_rate=fee,
        target_fee_rate=fee,
        market_exit_fee_rate=fee,
        liquidation_fee_rate=fee,
        entry_slippage_bps=0.0,
        market_exit_slippage_bps=0.0,
        reentry_cooldown_bars=1,
        open_bid_column="open_bid",
        open_ask_column="open_ask",
        close_bid_column="close_bid",
        close_ask_column="close_ask",
    )


def _selection_key(trial: MuTrial) -> tuple[float, ...]:
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


def _scenario_costs(
    friction: MuDepthFriction, stress: bool
) -> tuple[float, float, float]:
    if stress:
        return (
            friction.regular_round_trip_p99_bps / 2.0,
            friction.outside_round_trip_p99_bps / 2.0,
            friction.stress_latency_bps_per_side,
        )
    return (
        friction.regular_round_trip_p90_bps / 2.0,
        friction.outside_round_trip_p90_bps / 2.0,
        friction.nominal_latency_bps_per_side,
    )


def _trade_diagnostics(
    trades: tuple[SharedPortfolioTrade, ...],
) -> TradeDiagnostics:
    pnl = [trade.net_pnl_usd for trade in trades]
    largest = max((value for value in pnl if value > 0.0), default=0.0)
    reduced = pnl.copy()
    if largest > 0.0:
        reduced.remove(largest)
    return TradeDiagnostics(
        len(pnl),
        sum(value > 0.0 for value in pnl),
        sum(value < 0.0 for value in pnl),
        sum(value == 0.0 for value in pnl),
        sum(pnl),
        _profit_factor(pnl),
        largest,
        sum(reduced),
        _profit_factor(reduced),
    )


def _profit_factor(values: list[float]) -> float | None:
    gains = sum(value for value in values if value > 0.0)
    losses = -sum(value for value in values if value < 0.0)
    return gains / losses if losses > 0.0 else None


def _trade_session(trade: SharedPortfolioTrade) -> str:
    return _session_name(pd.Timestamp(trade.entry_time_utc))


def _session_name(timestamp: pd.Timestamp) -> str:
    local = timestamp.tz_convert(_NEW_YORK)
    clock_minutes = local.hour * 60 + local.minute
    regular = local.weekday() < 5 and 570 <= clock_minutes < 960
    return "us_regular_hours" if regular else "outside_us_regular_hours"


def _fold_bounds(
    index: pd.DatetimeIndex, development_position: int
) -> tuple[tuple[pd.Timestamp, pd.Timestamp], ...]:
    first = development_position // 3
    second = 2 * development_position // 3
    if first < 2 or second <= first or development_position <= second:
        raise ValueError("MU development window is too short for three folds")
    return (
        (index[0], index[first]),
        (index[first], index[second]),
        (index[second], index[development_position]),
    )


def _validate_index(index: pd.DatetimeIndex) -> None:
    if index.tz is None or index.empty:
        raise ValueError("MU bars require a non-empty timezone-aware index")
    if not index.is_monotonic_increasing or not index.is_unique:
        raise ValueError("MU bars require ordered unique timestamps")


def _validate_bars(bars: pd.DataFrame) -> None:
    _validate_index(bars.index)
    required = {"open", "high", "low", "close", "gap_before_bars", "funding_rate"}
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise ValueError(f"MU bars missing required columns: {missing}")
