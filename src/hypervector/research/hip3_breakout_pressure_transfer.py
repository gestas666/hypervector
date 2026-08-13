"""Chronological transfer screen for HIP-3 breakout-pressure challengers."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
    build_breakout_pressure_signals,
)
from hypervector.research.hip3_swing_transfer import (
    Hip3ExecutionFriction,
    Hip3TransferAsset,
    Hip3TransferWindows,
    common_transfer_windows,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)

_INITIAL_EQUITY = 500.0
_NOTIONAL_USD = 75.0
_LEVERAGE = 5.0
_MAX_HOLD_BARS = 96


@dataclass(frozen=True)
class Hip3BreakoutTrial:
    """One fully reported development configuration and fold evidence."""

    config: Hip3BreakoutPressureConfig
    development: tuple[tuple[str, SharedPortfolioReport], ...]
    folds: tuple[tuple[str, SharedPortfolioReport], ...]

    @property
    def positive_fold_count(self) -> int:
        """Return development folds with positive net results."""
        return sum(report.net_pnl_usd > 0.0 for _, report in self.folds)

    @property
    def active_fold_count(self) -> int:
        """Return development folds that completed at least one trade."""
        return sum(report.completed_trades > 0 for _, report in self.folds)

    @property
    def completed_fold_trades(self) -> int:
        """Return all completed fold trades without deduplicating overlaps."""
        return sum(report.completed_trades for _, report in self.folds)

    @property
    def minimum_fold_net_pnl(self) -> float:
        """Return the weakest development fold result."""
        return min((report.net_pnl_usd for _, report in self.folds), default=0.0)

    @property
    def pooled_fold_net_pnl(self) -> float:
        """Return the summed fold result used only for selection ordering."""
        return sum(report.net_pnl_usd for _, report in self.folds)


@dataclass(frozen=True)
class Hip3BreakoutValidation:
    """One untouched validation cell under a named friction condition."""

    symbol: str
    friction: str
    report: SharedPortfolioReport


@dataclass(frozen=True)
class Hip3BreakoutTransferResult:
    """Searched development trials and validation-only selected result."""

    windows: Hip3TransferWindows
    trials: tuple[Hip3BreakoutTrial, ...]
    selected_config: Hip3BreakoutPressureConfig
    validation_nominal: tuple[Hip3BreakoutValidation, ...]
    validation_stress: tuple[Hip3BreakoutValidation, ...]
    holdout_status: str = "sealed_not_evaluated"
    execution_authority: str = "none"


def default_breakout_pressure_grid() -> tuple[Hip3BreakoutPressureConfig, ...]:
    """Return the explicit finite development search surface."""
    return tuple(
        Hip3BreakoutPressureConfig(lookback, fast, slow, pressure, stop)
        for lookback in (4, 8, 16, 32)
        for fast, slow in ((3, 8), (5, 13), (9, 21), (21, 55))
        for pressure in (0.10, 0.20, 0.35, 0.50)
        for stop in (40.0, 80.0, 120.0)
    )


def run_hip3_breakout_pressure_transfer(
    assets: tuple[Hip3TransferAsset, ...],
    frictions: dict[str, Hip3ExecutionFriction],
    *,
    configs: tuple[Hip3BreakoutPressureConfig, ...] | None = None,
) -> Hip3BreakoutTransferResult:
    """Search development, freeze one recipe, and evaluate validation only."""
    _validate_inputs(assets, frictions)
    windows = common_transfer_windows(assets)
    candidates = configs or default_breakout_pressure_grid()
    if not candidates or len(set(candidates)) != len(candidates):
        raise ValueError("HIP-3 breakout grid must be non-empty and unique")
    trials = tuple(
        _evaluate_development(assets, frictions, windows, config)
        for config in candidates
    )
    selected = max(trials, key=_selection_key).config
    nominal = _evaluate_validation(assets, frictions, windows, selected, False)
    stress = _evaluate_validation(assets, frictions, windows, selected, True)
    return Hip3BreakoutTransferResult(
        windows,
        trials,
        selected,
        nominal,
        stress,
    )


def quote_aware_portfolio_config(
    asset: Hip3TransferAsset,
    friction: Hip3ExecutionFriction,
    *,
    stress: bool,
) -> SharedPortfolioConfig:
    """Map measured fees, quotes, and explicit latency into the simulator."""
    leverage = min(_LEVERAGE, asset.venue_max_leverage)
    latency = (
        friction.stress_latency_bps_per_side
        if stress
        else friction.nominal_latency_bps_per_side
    )
    tail_delta = 0.0
    if stress:
        tail_delta = (
            max(
                friction.stress_visible_round_trip_bps
                - friction.nominal_visible_round_trip_bps,
                0.0,
            )
            / 2.0
        )
    return SharedPortfolioConfig(
        symbol=asset.symbol,
        initial_equity=_INITIAL_EQUITY,
        margin_fraction=_NOTIONAL_USD / (_INITIAL_EQUITY * leverage),
        leverage=leverage,
        venue_max_leverage=asset.venue_max_leverage,
        entry_fee_rate=friction.effective_taker_fee_rate,
        target_fee_rate=friction.effective_taker_fee_rate,
        market_exit_fee_rate=friction.effective_taker_fee_rate,
        liquidation_fee_rate=friction.effective_taker_fee_rate,
        entry_slippage_bps=latency + tail_delta,
        market_exit_slippage_bps=latency + tail_delta,
        max_hold_bars=_MAX_HOLD_BARS,
        reentry_cooldown_bars=1,
        same_direction_reentry_requires_reset=True,
        close_on_opposite_signal=True,
        reverse_on_opposite_signal=False,
        open_bid_column="entry_bid",
        open_ask_column="entry_ask",
        close_bid_column="decision_bid",
        close_ask_column="decision_ask",
    )


def _evaluate_development(
    assets: tuple[Hip3TransferAsset, ...],
    frictions: dict[str, Hip3ExecutionFriction],
    windows: Hip3TransferWindows,
    config: Hip3BreakoutPressureConfig,
) -> Hip3BreakoutTrial:
    full: list[tuple[str, SharedPortfolioReport]] = []
    folds: list[tuple[str, SharedPortfolioReport]] = []
    for asset in assets:
        bars, signals = _research_inputs(asset, config, windows)
        portfolio = quote_aware_portfolio_config(
            asset, frictions[asset.symbol], stress=False
        )
        full.append(
            (
                asset.symbol,
                _window_report(
                    bars,
                    signals,
                    windows.development_start_utc,
                    windows.development_end_utc,
                    portfolio,
                ),
            )
        )
        folds.extend(
            (asset.symbol, _window_report(bars, signals, start, end, portfolio))
            for start, end in windows.development_folds
        )
    return Hip3BreakoutTrial(config, tuple(full), tuple(folds))


def _evaluate_validation(
    assets: tuple[Hip3TransferAsset, ...],
    frictions: dict[str, Hip3ExecutionFriction],
    windows: Hip3TransferWindows,
    config: Hip3BreakoutPressureConfig,
    stress: bool,
) -> tuple[Hip3BreakoutValidation, ...]:
    cells: list[Hip3BreakoutValidation] = []
    for asset in assets:
        bars, signals = _research_inputs(asset, config, windows)
        portfolio = quote_aware_portfolio_config(
            asset, frictions[asset.symbol], stress=stress
        )
        report = _window_report(
            bars,
            signals,
            windows.development_end_utc,
            windows.validation_end_utc,
            portfolio,
        )
        cells.append(
            Hip3BreakoutValidation(
                asset.symbol, "stress" if stress else "nominal", report
            )
        )
    return tuple(cells)


def _research_inputs(
    asset: Hip3TransferAsset,
    config: Hip3BreakoutPressureConfig,
    windows: Hip3TransferWindows,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    selected = asset.bars.index.to_series().ge(windows.development_start_utc)
    selected &= asset.bars.index.to_series().lt(windows.validation_end_utc)
    bars = asset.bars.loc[selected].copy()
    return bars, build_breakout_pressure_signals(bars, config)


def _window_report(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    config: SharedPortfolioConfig,
) -> SharedPortfolioReport:
    selected = bars.index.to_series().ge(start) & bars.index.to_series().lt(end)
    return evaluate_shared_bar_portfolio(
        bars.loc[selected].copy(),
        signals.loc[selected].copy(),
        config,
    )


def _selection_key(trial: Hip3BreakoutTrial) -> tuple[int, int, float, float, int]:
    return (
        trial.positive_fold_count,
        trial.active_fold_count,
        trial.minimum_fold_net_pnl,
        trial.pooled_fold_net_pnl,
        trial.completed_fold_trades,
    )


def _validate_inputs(
    assets: tuple[Hip3TransferAsset, ...],
    frictions: dict[str, Hip3ExecutionFriction],
) -> None:
    if not assets or len({asset.symbol for asset in assets}) != len(assets):
        raise ValueError("HIP-3 breakout assets must be non-empty and unique")
    if set(frictions) != {asset.symbol for asset in assets}:
        raise ValueError("HIP-3 breakout friction scope must match assets")
    required = {
        "entry_bid",
        "entry_ask",
        "decision_bid",
        "decision_ask",
        "decision_imbalance_10",
    }
    for asset in assets:
        missing = required.difference(asset.bars.columns)
        if missing:
            raise ValueError(
                f"{asset.symbol} breakout transfer bars missing: {sorted(missing)}"
            )
