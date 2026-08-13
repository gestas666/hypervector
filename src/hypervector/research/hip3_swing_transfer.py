"""Bounded chronological Swing/HA transfer experiment for HIP-3 markets."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import pandas as pd

from hypervector.data.oxa_api import validate_hip3_symbol
from hypervector.research.hip3_swing_signals import (
    build_gap_aware_swing_ha_signals,
)
from hypervector.research.swing_ha_experiment import (
    SwingHaEvaluation,
    selected_from_evaluations,
)
from hypervector.research.swing_ha_screen import (
    SwingHaScreenCell,
    SwingHaScreenConfig,
    base_trial_grid,
    evaluate_swing_ha_cell,
    order_block_trial_grid,
)
from hypervector.research.swing_ha_signals import SwingHaSignalConfig

_BAR_MINUTES = 15
_DEFAULT_INITIAL_EQUITY = 500.0
_DEFAULT_LEVERAGE = 5.0


@dataclass(frozen=True)
class Hip3TransferAsset:
    """One exact HIP-3 market and its funded midpoint bars."""

    symbol: str
    venue_max_leverage: float
    bars: pd.DataFrame

    def __post_init__(self) -> None:
        """Reject malformed identities while leaving sealed prices unread."""
        validate_hip3_symbol(self.symbol)
        if not isfinite(self.venue_max_leverage) or self.venue_max_leverage <= 0.0:
            raise ValueError("HIP-3 venue max leverage must be positive")
        required = {"open", "high", "low", "close", "gap_before_bars", "funding_rate"}
        missing = sorted(required.difference(self.bars.columns))
        if missing:
            raise ValueError(f"HIP-3 transfer bars missing columns: {missing}")
        index = self.bars.index
        if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
            raise ValueError("HIP-3 transfer bars require a timezone-aware index")
        if index.empty or not index.is_monotonic_increasing or not index.is_unique:
            raise ValueError("HIP-3 transfer bars require ordered unique rows")


@dataclass(frozen=True)
class Hip3ExecutionFriction:
    """Measured fee/depth evidence plus explicit latency allowances."""

    notional_usd: float
    effective_taker_fee_rate: float
    nominal_visible_round_trip_bps: float
    nominal_latency_bps_per_side: float
    stress_visible_round_trip_bps: float
    stress_latency_bps_per_side: float

    def __post_init__(self) -> None:
        """Reject non-finite or economically invalid cost evidence."""
        positive = (self.notional_usd, self.effective_taker_fee_rate)
        nonnegative = (
            self.nominal_visible_round_trip_bps,
            self.nominal_latency_bps_per_side,
            self.stress_visible_round_trip_bps,
            self.stress_latency_bps_per_side,
        )
        if any(not isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("HIP-3 notional and taker fee must be positive")
        if any(not isfinite(value) or value < 0.0 for value in nonnegative):
            raise ValueError("HIP-3 visible and latency costs must be non-negative")

    def screen_config(self, *, stress: bool) -> SwingHaScreenConfig:
        """Map the measured `$75` contract into the shared simulator."""
        visible = (
            self.stress_visible_round_trip_bps
            if stress
            else self.nominal_visible_round_trip_bps
        )
        latency = (
            self.stress_latency_bps_per_side
            if stress
            else self.nominal_latency_bps_per_side
        )
        slippage = visible / 2.0 + latency
        margin_fraction = self.notional_usd / (
            _DEFAULT_INITIAL_EQUITY * _DEFAULT_LEVERAGE
        )
        return SwingHaScreenConfig(
            initial_equity=_DEFAULT_INITIAL_EQUITY,
            margin_fraction=margin_fraction,
            leverage=_DEFAULT_LEVERAGE,
            fee_rate_per_side=self.effective_taker_fee_rate,
            slippage_bps_per_side=slippage,
        )


@dataclass(frozen=True)
class Hip3TransferWindows:
    """Common chronological development, validation, and sealed holdout."""

    development_start_utc: pd.Timestamp
    development_end_utc: pd.Timestamp
    validation_end_utc: pd.Timestamp
    holdout_end_utc: pd.Timestamp
    development_folds: tuple[tuple[pd.Timestamp, pd.Timestamp], ...]


@dataclass(frozen=True)
class Hip3SwingTransferResult:
    """Complete searched trials and untouched-holdout validation result."""

    windows: Hip3TransferWindows
    base_evaluations: tuple[SwingHaEvaluation, ...]
    selected_base: SwingHaSignalConfig
    order_block_evaluations: tuple[SwingHaEvaluation, ...]
    selected_frozen: SwingHaSignalConfig
    validation_nominal: tuple[SwingHaScreenCell, ...]
    validation_stress: tuple[SwingHaScreenCell, ...]
    literal_control: SwingHaSignalConfig
    literal_control_nominal: tuple[SwingHaScreenCell, ...]
    literal_control_stress: tuple[SwingHaScreenCell, ...]
    holdout_status: str = "sealed_not_evaluated"
    execution_authority: str = "none"

    @property
    def searched_trial_count(self) -> int:
        """Return every development configuration inspected."""
        return len(self.base_evaluations) + len(self.order_block_evaluations)


def common_transfer_windows(
    assets: tuple[Hip3TransferAsset, ...],
) -> Hip3TransferWindows:
    """Return aligned 60/20/20 windows over common observable coverage."""
    if not assets:
        raise ValueError("HIP-3 transfer requires at least one asset")
    start = max(asset.bars.index.min() for asset in assets)
    end = min(asset.bars.index.max() for asset in assets) + pd.Timedelta(
        minutes=_BAR_MINUTES
    )
    if end - start < pd.Timedelta(hours=6):
        raise ValueError("HIP-3 common coverage is too short")
    development_end = _aligned_fraction(start, end, 0.60)
    validation_end = _aligned_fraction(start, end, 0.80)
    folds = _folds(start, development_end)
    return Hip3TransferWindows(start, development_end, validation_end, end, folds)


def literal_swing_control_config() -> SwingHaSignalConfig:
    """Return the pre-registered BUY+green / SELL+red 9/21 control."""
    return SwingHaSignalConfig(
        fast_ema=9,
        slow_ema=21,
        pivot_length=5,
        entry_mode="state",
        exit_mode="alignment_loss",
        order_block_role="none",
    )


def run_hip3_swing_transfer(
    assets: tuple[Hip3TransferAsset, ...],
    frictions: dict[str, Hip3ExecutionFriction],
    *,
    base_configs: tuple[SwingHaSignalConfig, ...] | None = None,
    order_block_configs: tuple[SwingHaSignalConfig, ...] | None = None,
) -> Hip3SwingTransferResult:
    """Select on development and evaluate validation without opening holdout."""
    _validate_inputs(assets, frictions)
    windows = common_transfer_windows(assets)
    bases = base_configs or base_trial_grid()
    if not bases:
        raise ValueError("HIP-3 transfer base grid must be non-empty")
    base_evaluations = _evaluate_grid(assets, frictions, bases, windows)
    selected_base = selected_from_evaluations(base_evaluations)
    blocks = order_block_configs or order_block_trial_grid(selected_base)
    if not blocks:
        raise ValueError("HIP-3 transfer order-block grid must be non-empty")
    block_evaluations = _evaluate_grid(assets, frictions, blocks, windows)
    selected = selected_from_evaluations(block_evaluations)
    nominal = _evaluate_validation(assets, frictions, selected, windows, False)
    stress = _evaluate_validation(assets, frictions, selected, windows, True)
    control = literal_swing_control_config()
    control_nominal = _evaluate_validation(assets, frictions, control, windows, False)
    control_stress = _evaluate_validation(assets, frictions, control, windows, True)
    return Hip3SwingTransferResult(
        windows,
        base_evaluations,
        selected_base,
        block_evaluations,
        selected,
        nominal,
        stress,
        control,
        control_nominal,
        control_stress,
    )


def _evaluate_grid(
    assets: tuple[Hip3TransferAsset, ...],
    frictions: dict[str, Hip3ExecutionFriction],
    configs: tuple[SwingHaSignalConfig, ...],
    windows: Hip3TransferWindows,
) -> tuple[SwingHaEvaluation, ...]:
    evaluations: list[SwingHaEvaluation] = []
    for config in configs:
        full: list[SwingHaScreenCell] = []
        folds: list[SwingHaScreenCell] = []
        for asset in assets:
            bars, signals = _research_inputs(asset, config, windows)
            screen = frictions[asset.symbol].screen_config(stress=False)
            full.append(
                _window_cell(
                    asset,
                    bars,
                    signals,
                    config,
                    screen,
                    windows.development_start_utc,
                    windows.development_end_utc,
                )
            )
            folds.extend(
                _window_cell(asset, bars, signals, config, screen, start, end)
                for start, end in windows.development_folds
            )
        evaluations.append(SwingHaEvaluation(config, tuple(full), tuple(folds)))
    return tuple(evaluations)


def _evaluate_validation(
    assets: tuple[Hip3TransferAsset, ...],
    frictions: dict[str, Hip3ExecutionFriction],
    config: SwingHaSignalConfig,
    windows: Hip3TransferWindows,
    stress: bool,
) -> tuple[SwingHaScreenCell, ...]:
    cells: list[SwingHaScreenCell] = []
    for asset in assets:
        bars, signals = _research_inputs(asset, config, windows)
        cells.append(
            _window_cell(
                asset,
                bars,
                signals,
                config,
                frictions[asset.symbol].screen_config(stress=stress),
                windows.development_end_utc,
                windows.validation_end_utc,
            )
        )
    return tuple(cells)


def _research_inputs(
    asset: Hip3TransferAsset,
    config: SwingHaSignalConfig,
    windows: Hip3TransferWindows,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    selected = asset.bars.index.to_series().ge(windows.development_start_utc)
    selected &= asset.bars.index.to_series().lt(windows.validation_end_utc)
    bars = asset.bars.loc[selected].copy()
    signals = build_gap_aware_swing_ha_signals(bars, config)
    return bars, signals


def _window_cell(
    asset: Hip3TransferAsset,
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    config: SwingHaSignalConfig,
    screen: SwingHaScreenConfig,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> SwingHaScreenCell:
    selected = bars.index.to_series().ge(start) & bars.index.to_series().lt(end)
    window_bars = bars.loc[selected].copy()
    window_signals = signals.loc[selected].copy()
    _expire_gap_through_stops(window_bars, window_signals)
    return evaluate_swing_ha_cell(
        window_bars,
        window_signals,
        symbol=asset.symbol,
        signal_config=config,
        venue_max_leverage=asset.venue_max_leverage,
        screen_config=screen,
    )


def _expire_gap_through_stops(bars: pd.DataFrame, signals: pd.DataFrame) -> None:
    next_open = bars["open"].shift(-1)
    stop = signals["stop_price"]
    invalid_long = signals["long_entry"] & stop.notna() & stop.ge(next_open)
    invalid_short = signals["short_entry"] & stop.notna() & stop.le(next_open)
    signals.loc[invalid_long, "long_entry"] = False
    signals.loc[invalid_short, "short_entry"] = False


def _validate_inputs(
    assets: tuple[Hip3TransferAsset, ...],
    frictions: dict[str, Hip3ExecutionFriction],
) -> None:
    symbols = [asset.symbol for asset in assets]
    if not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("HIP-3 transfer assets must be non-empty and unique")
    if set(symbols) != set(frictions):
        raise ValueError("HIP-3 transfer friction scope must match asset scope")


def _aligned_fraction(
    start: pd.Timestamp,
    end: pd.Timestamp,
    fraction: float,
) -> pd.Timestamp:
    value = start + (end - start) * fraction
    return value.floor(f"{_BAR_MINUTES}min")


def _folds(
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[tuple[pd.Timestamp, pd.Timestamp], ...]:
    first = _aligned_fraction(start, end, 1.0 / 3.0)
    second = _aligned_fraction(start, end, 2.0 / 3.0)
    if not start < first < second < end:
        raise ValueError("HIP-3 development coverage is too short for three folds")
    return ((start, first), (first, second), (second, end))
